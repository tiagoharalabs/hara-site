import { DurableObject } from "cloudflare:workers";

const CHANNEL_SCHEMA = "hara.commander-device-channel.v2";
const EVENT_SCHEMA = "hara.commander-device-event.v2";
const MAX_NOTIFY_BYTES = 4096;

function nowIso() {
  return new Date().toISOString();
}

async function markConnected(env, tenantId, deviceId) {
  if (!env.PRODUCT_DB) throw new Error("CHANNEL_PRODUCT_DB_REQUIRED");
  const seenAt = nowIso();
  const result = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET tunnel_mode = 'EVENT_V2', last_seen_at_utc = ?
      WHERE tenant_id = ?
        AND device_id = ?
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL`
  ).bind(seenAt, tenantId, deviceId).run();
  if (!result.meta?.changes) throw new Error("CHANNEL_DEVICE_NOT_ACTIVE");
  return seenAt;
}

async function refreshLiveness(env, tenantId, deviceId) {
  if (!env.PRODUCT_DB) throw new Error("CHANNEL_PRODUCT_DB_REQUIRED");
  const seenAt = nowIso();
  const result = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET last_seen_at_utc = ?
      WHERE tenant_id = ?
        AND device_id = ?
        AND tunnel_mode = 'EVENT_V2'
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL`
  ).bind(seenAt, tenantId, deviceId).run();
  if (!result.meta?.changes) throw new Error("CHANNEL_DEVICE_NOT_ACTIVE");
  return seenAt;
}

async function markDisconnected(env, attachment) {
  if (!attachment || attachment.superseded) return;
  const tenantId = cleanIdentifier(attachment.tenant_id, 180);
  const deviceId = cleanIdentifier(attachment.device_id, 180);
  const seenAt = nowIso();
  await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET tunnel_mode = 'EVENT_V2_OFFLINE', last_seen_at_utc = ?
      WHERE tenant_id = ?
        AND device_id = ?
        AND tunnel_mode = 'EVENT_V2'
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL`
  ).bind(seenAt, tenantId, deviceId).run();
}

function cleanIdentifier(value, max = 220) {
  const text = String(value || "").trim();
  if (!text || text.length > max || !/^[A-Za-z0-9_.:-]+$/.test(text)) {
    throw new Error("CHANNEL_IDENTIFIER_INVALID");
  }
  return text;
}

function requireAuthenticatedInternalRequest(request) {
  if (request.headers.get("x-hara-channel-authenticated") !== "1") {
    throw new Error("CHANNEL_INTERNAL_AUTH_REQUIRED");
  }
}

function json(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });
}

function boundedBody(value) {
  const raw = JSON.stringify(value == null ? {} : value);
  if (new TextEncoder().encode(raw).byteLength > MAX_NOTIFY_BYTES) {
    throw new Error("CHANNEL_MESSAGE_TOO_LARGE");
  }
  return value;
}

export function deviceChannelName(tenantId, deviceId) {
  return cleanIdentifier(tenantId, 180) + ":" + cleanIdentifier(deviceId, 180);
}

export class DeviceChannel extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);
    try {
      requireAuthenticatedInternalRequest(request);

      if (url.pathname === "/connect" && request.method === "GET") {
        if (String(request.headers.get("upgrade") || "").toLowerCase() !== "websocket") {
          return new Response("Expected WebSocket upgrade", { status: 426 });
        }

        const tenantId = cleanIdentifier(request.headers.get("x-hara-tenant-id"), 180);
        const deviceId = cleanIdentifier(request.headers.get("x-hara-device-id"), 180);

        await markConnected(this.env, tenantId, deviceId);

        for (const prior of this.ctx.getWebSockets()) {
          try {
            const priorAttachment = prior.deserializeAttachment() || {};
            prior.serializeAttachment({
              ...priorAttachment,
              superseded: true,
            });
            prior.close(4001, "SUPERSEDED_BY_NEW_CHANNEL");
          } catch (_error) {
            // Best effort only. The new authenticated channel remains authoritative.
          }
        }

        const pair = new WebSocketPair();
        const [client, server] = Object.values(pair);

        server.serializeAttachment({
          schema: CHANNEL_SCHEMA,
          tenant_id: tenantId,
          device_id: deviceId,
          superseded: false,
        });
        this.ctx.acceptWebSocket(server, [
          "tenant:" + tenantId,
          "device:" + deviceId,
        ]);

        return new Response(null, { status: 101, webSocket: client });
      }

      if (url.pathname === "/notify" && request.method === "POST") {
        const body = boundedBody(await request.json());
        const callId = cleanIdentifier(body.call_id, 180);
        const event = JSON.stringify({
          schema: EVENT_SCHEMA,
          type: "CALL_AVAILABLE",
          call_id: callId,
        });

        let delivered = 0;
        for (const socket of this.ctx.getWebSockets()) {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(event);
            delivered += 1;
          }
        }

        return json({
          schema: CHANNEL_SCHEMA,
          ok: true,
          delivered,
          call_id: callId,
        });
      }

      if (url.pathname === "/status" && request.method === "GET") {
        return json({
          schema: CHANNEL_SCHEMA,
          connected: this.ctx.getWebSockets().filter(
            (socket) => socket.readyState === WebSocket.OPEN
          ).length,
        });
      }

      return json({ ok: false, code: "CHANNEL_ROUTE_NOT_FOUND" }, 404);
    } catch (error) {
      const raw = String(error?.message || "CHANNEL_INTERNAL_ERROR");
      const code = /^[A-Z][A-Z0-9_]{0,119}$/.test(raw)
        ? raw
        : "CHANNEL_INTERNAL_ERROR";
      const status = code === "CHANNEL_INTERNAL_AUTH_REQUIRED" ? 401 : 400;
      return json({ ok: false, code }, status);
    }
  }

  async webSocketMessage(socket, message) {
    let payload;
    try {
      const raw = typeof message === "string"
        ? message
        : new TextDecoder().decode(message);
      if (new TextEncoder().encode(raw).byteLength > MAX_NOTIFY_BYTES) {
        throw new Error("CHANNEL_MESSAGE_TOO_LARGE");
      }
      payload = JSON.parse(raw);
    } catch (_error) {
      socket.close(1008, "CHANNEL_MESSAGE_INVALID");
      return;
    }

    if (
      payload
      && payload.schema === EVENT_SCHEMA
      && payload.type === "PING"
      && Object.keys(payload).sort().join(",") === "schema,type"
    ) {
      socket.send(JSON.stringify({
        schema: EVENT_SCHEMA,
        type: "PONG",
      }));
      return;
    }

    if (
      payload
      && payload.schema === EVENT_SCHEMA
      && payload.type === "LIVENESS"
      && Object.keys(payload).sort().join(",") === "schema,type"
    ) {
      const attachment = socket.deserializeAttachment();
      try {
        await refreshLiveness(
          this.env,
          attachment?.tenant_id,
          attachment?.device_id,
        );
      } catch (_error) {
        try {
          socket.close(1011, "CHANNEL_LIVENESS_FAILED");
        } catch (_closeError) {
          // Best effort only.
        }
      }
      return;
    }

    socket.close(1008, "CHANNEL_MESSAGE_DENIED");
  }

  async webSocketClose(socket, _code, _reason, _wasClean) {
    // Cloudflare compatibility dates >= 2026-04-07 auto-complete close handshakes.
    try {
      await markDisconnected(this.env, socket.deserializeAttachment());
    } catch (_error) {
      // Presence will fail stale after the bounded Event V2 liveness window.
    }
  }

  webSocketError(socket, _error) {
    try {
      socket.close(1011, "CHANNEL_SOCKET_ERROR");
    } catch (_closeError) {
      // Connection may already be gone.
    }
  }
}
