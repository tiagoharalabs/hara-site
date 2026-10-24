import { DurableObject } from "cloudflare:workers";
import { canonicalChannelTelemetry, telemetryRollupQuery } from "./device-telemetry.mjs";

const CHANNEL_SCHEMA = "hara.commander-device-channel.v2";
const EVENT_SCHEMA = "hara.commander-device-event.v2";
const MAX_NOTIFY_BYTES = 4096;
const CONNECT_REFRESH_MS = 5 * 60 * 60 * 1000;
const OFFLINE_GRACE_BASE_MS = 30 * 1000;
const OFFLINE_GRACE_JITTER_MS = 30 * 1000;
const PENDING_OFFLINE_KEY = "pending_offline";
const MAX_TRANSIENT_REQUEST_BYTES = 160 * 1024;
const MAX_TRANSIENT_RESULT_BYTES = 320 * 1024;
const TRANSIENT_RPC_TIMEOUT_MS = 45 * 1000;
const MAX_TRANSIENT_INFLIGHT = 1;
const PROBE_REQUEST = 'HARA_EVENT_V2_PROBE_V1';
const PROBE_RESPONSE = 'HARA_EVENT_V2_PROBE_ACK_V1';

function currentSockets(ctx) {
  return ctx.getWebSockets().filter(socket => {
    if (socket.readyState !== WebSocket.OPEN) return false;
    try {
      const attachment=socket.deserializeAttachment();
      return Boolean(attachment && !attachment.superseded);
    } catch { return false; }
  });
}

function nowIso() {
  return new Date().toISOString();
}

function stableJitterMs(value) {
  let hash = 2166136261;
  for (const char of String(value || "")) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % OFFLINE_GRACE_JITTER_MS;
}

async function clearPendingOffline(ctx) {
  await ctx.storage.deleteAlarm();
  await ctx.storage.delete(PENDING_OFFLINE_KEY);
}

async function markConnected(env, tenantId, deviceId) {
  if (!env.PRODUCT_DB) throw new Error("CHANNEL_PRODUCT_DB_REQUIRED");
  const seenAt = nowIso();
  const refreshCutoff = new Date(Date.now() - CONNECT_REFRESH_MS).toISOString();
  const result = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET tunnel_mode = 'EVENT_V2', last_seen_at_utc = ?
      WHERE tenant_id = ?
        AND device_id = ?
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL
        AND (
          tunnel_mode != 'EVENT_V2'
          OR last_seen_at_utc IS NULL
          OR last_seen_at_utc < ?
        )`
  ).bind(seenAt, tenantId, deviceId, refreshCutoff).run();

  // Authentication and this D1 write are separate async boundaries. A zero
  // update can also mean concurrent revocation; never accept it blindly.
  if (!result.meta?.changes) {
    const active=await env.PRODUCT_DB.prepare(
      "SELECT 1 AS active FROM commander_devices WHERE tenant_id=? AND device_id=? "+
      "AND state='ACTIVE' AND revoked_at_utc IS NULL AND tunnel_mode='EVENT_V2'"
    ).bind(tenantId,deviceId).first();
    if (!active) throw new Error("CHANNEL_DEVICE_NOT_ACTIVE");
  }
  return {
    seen_at_utc: seenAt,
    durable_write: Boolean(result.meta?.changes),
  };
}

async function refreshLiveness(env, tenantId, deviceId, telemetry = null) {
  if (!env.PRODUCT_DB) throw new Error("CHANNEL_PRODUCT_DB_REQUIRED");
  const seenAt = nowIso();
  const liveness = env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET last_seen_at_utc = ?
      WHERE tenant_id = ?
        AND device_id = ?
        AND tunnel_mode = 'EVENT_V2'
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL`
  ).bind(seenAt, tenantId, deviceId);
  // Old Agents remain one D1 operation. Metrics use one atomic batch,
  // piggybacked on existing 6h LIVENESS: no new HTTP request or timer.
  const result = telemetry === null
    ? await liveness.run()
    : (await env.PRODUCT_DB.batch([
        liveness,
        telemetryRollupQuery(env, tenantId, deviceId, seenAt, telemetry),
      ]))[0];
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


async function scheduleDisconnected(ctx, attachment) {
  if (!attachment || attachment.superseded) return;

  const stillConnected = currentSockets(ctx).length > 0;
  if (stillConnected) return;

  const tenantId = cleanIdentifier(attachment.tenant_id, 180);
  const deviceId = cleanIdentifier(attachment.device_id, 180);
  const dueAtMs = Date.now()
    + OFFLINE_GRACE_BASE_MS
    + stableJitterMs(deviceId);

  await ctx.storage.put(PENDING_OFFLINE_KEY, {
    tenant_id: tenantId,
    device_id: deviceId,
    scheduled_at_ms: dueAtMs,
  });
  await ctx.storage.setAlarm(dueAtMs);
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

function boundedBody(value, maxBytes = MAX_NOTIFY_BYTES) {
  const raw = JSON.stringify(value == null ? {} : value);
  if (new TextEncoder().encode(raw).byteLength > maxBytes) {
    throw new Error("CHANNEL_MESSAGE_TOO_LARGE");
  }
  return value;
}

function cleanLearningSignal(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("CHANNEL_LEARNING_SIGNAL_INVALID");
  }
  const allowed = [
    "schema",
    "tool_id",
    "tool_family",
    "outcome",
    "latency_bucket",
    "result_bytes_bucket",
    "platform",
    "agent_version",
    "transport_mode",
    "privileged_attempt",
    "customer_content_collected",
  ];
  const keys = Object.keys(value).sort();
  if (keys.join(",") !== [...allowed].sort().join(",")) {
    throw new Error("CHANNEL_LEARNING_SIGNAL_INVALID");
  }
  if (value.schema !== "hara.commander-learning-signal.v1") {
    throw new Error("CHANNEL_LEARNING_SIGNAL_INVALID");
  }
  if (value.privileged_attempt !== false || value.customer_content_collected !== false) {
    throw new Error("CHANNEL_LEARNING_SIGNAL_INVALID");
  }
  return {
    schema: value.schema,
    tool_id: cleanIdentifier(value.tool_id, 120),
    tool_family: cleanIdentifier(value.tool_family, 80),
    outcome: cleanIdentifier(value.outcome, 40),
    latency_bucket: cleanIdentifier(value.latency_bucket, 40),
    result_bytes_bucket: cleanIdentifier(value.result_bytes_bucket, 40),
    platform: cleanIdentifier(value.platform, 40),
    agent_version: cleanIdentifier(value.agent_version, 80),
    transport_mode: cleanIdentifier(value.transport_mode, 40),
    privileged_attempt: false,
    customer_content_collected: false,
  };
}

export function deviceChannelName(tenantId, deviceId) {
  return cleanIdentifier(tenantId, 180) + ":" + cleanIdentifier(deviceId, 180);
}

export class DeviceChannel extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    this.env = env;
    this.pendingTransient = new Map();
    this.presenceTail=Promise.resolve();
    // Static probes remain in the hibernation runtime, without D1 writes or
    // waking a JS handler. https://developers.cloudflare.com/durable-objects/api/state/#setwebsocketautoresponse
    if (typeof ctx.setWebSocketAutoResponse === 'function') {
      ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair(PROBE_REQUEST,PROBE_RESPONSE));
    }
  }

  withPresence(action) {
    // Serialize only connect/close/alarm presence writes. A long transient RPC
    // must not hold this fence or prevent its socket result from arriving.
    const operation=this.presenceTail.then(action);
    this.presenceTail=operation.catch(()=>{});
    return operation;
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

        return await this.withPresence(async()=>{
        await clearPendingOffline(this.ctx);
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
        });
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
        for (const socket of currentSockets(this.ctx)) {
            socket.send(event);
            delivered += 1;
        }

        return json({
          schema: CHANNEL_SCHEMA,
          ok: true,
          delivered,
          call_id: callId,
        });
      }

      if (url.pathname === "/invalidate" && request.method === "POST") {
        const tenantId=cleanIdentifier(request.headers.get("x-hara-tenant-id"),180);
        const deviceId=cleanIdentifier(request.headers.get("x-hara-device-id"),180);
        return await this.withPresence(async()=>{
          const row=await this.env.PRODUCT_DB.prepare(
            "SELECT state,revoked_at_utc,tunnel_mode FROM commander_devices WHERE tenant_id=? AND device_id=?"
          ).bind(tenantId,deviceId).first();
          if(!row || (row.state==='ACTIVE'&&!row.revoked_at_utc&&
             !['EVENT_V2_OFFLINE','OUTBOUND_RELAY_OFFLINE'].includes(row.tunnel_mode)))throw new Error('CHANNEL_INVALIDATION_PRECONDITION');
          for(const socket of this.ctx.getWebSockets()){
            const attachment=socket.deserializeAttachment();
            if(attachment?.tenant_id!==tenantId||attachment?.device_id!==deviceId)continue;
            socket.serializeAttachment({...attachment,superseded:true});
            for(const [id,pending] of this.pendingTransient){
              if(pending.socket!==socket)continue;
              pending.reject(new Error('CHANNEL_TRANSIENT_DISCONNECTED'));
              this.pendingTransient.delete(id);
            }
            try{socket.close(4003,'CHANNEL_AUTHORIZATION_ENDED');}catch{}
          }
          await clearPendingOffline(this.ctx);
          return json({ok:true,invalidated:true});
        });
      }

      if (url.pathname === "/dispatch" && request.method === "POST") {
        const body = boundedBody(await request.json(), MAX_TRANSIENT_REQUEST_BYTES);
        const callId = cleanIdentifier(body.call_id, 180);
        const requestId = cleanIdentifier(body.request_id, 220);
        const toolId = cleanIdentifier(body.tool_id, 120);
        const executionMode = String(body.execution_mode || "").trim().toUpperCase();
        if (!["EXECUTE_OR_REPLAY", "REPLAY_ONLY"].includes(executionMode)) {
          throw new Error("CHANNEL_TRANSIENT_EXECUTION_MODE_INVALID");
        }
        if (!body.payload || typeof body.payload !== "object" || Array.isArray(body.payload)) {
          throw new Error("CHANNEL_TRANSIENT_PAYLOAD_INVALID");
        }
        if (this.pendingTransient.size >= MAX_TRANSIENT_INFLIGHT) {
          throw new Error("CHANNEL_TRANSIENT_BUSY");
        }

        const sockets = currentSockets(this.ctx);
        if (sockets.length < 1) throw new Error("CHANNEL_TRANSIENT_OFFLINE");
        const attachment=sockets[0].deserializeAttachment();
        const active=await this.env.PRODUCT_DB.prepare(
          "SELECT 1 AS active FROM commander_devices WHERE tenant_id=? AND device_id=? "+
          "AND state='ACTIVE' AND revoked_at_utc IS NULL AND tunnel_mode='EVENT_V2'"
        ).bind(attachment.tenant_id,attachment.device_id).first();
        // Revalidate after the external D1 await: reconnect/revocation may have
        // invalidated the originally selected socket while this request yielded.
        if(!active || !currentSockets(this.ctx).includes(sockets[0]))throw new Error('CHANNEL_DEVICE_NOT_ACTIVE');

        const event = JSON.stringify({
          schema: EVENT_SCHEMA,
          type: "CALL_TRANSIENT",
          call_id: callId,
          request_id: requestId,
          tool_id: toolId,
          execution_mode: executionMode,
          payload: body.payload,
        });
        if (new TextEncoder().encode(event).byteLength > MAX_TRANSIENT_REQUEST_BYTES) {
          throw new Error("CHANNEL_MESSAGE_TOO_LARGE");
        }

        let claim;
        const resultPromise = new Promise((resolve, reject) => {
          claim={ resolve, reject, socket:sockets[0] };
          this.pendingTransient.set(callId, claim);
        });

        try {
          sockets[0].send(event);
          const result = await Promise.race([
            resultPromise,
            scheduler.wait(TRANSIENT_RPC_TIMEOUT_MS).then(() => {
              throw new Error("CHANNEL_TRANSIENT_TIMEOUT");
            }),
          ]);
          return json(result);
        } finally {
          if(this.pendingTransient.get(callId)===claim)this.pendingTransient.delete(callId);
        }
      }

      if (url.pathname === "/status" && request.method === "GET") {
        return json({
          schema: CHANNEL_SCHEMA,
          connected: currentSockets(this.ctx).length,
        });
      }

      return json({ ok: false, code: "CHANNEL_ROUTE_NOT_FOUND" }, 404);
    } catch (error) {
      const raw = String(error?.message || "CHANNEL_INTERNAL_ERROR");
      const code = /^[A-Z][A-Z0-9_]{0,119}$/.test(raw)
        ? raw
        : "CHANNEL_INTERNAL_ERROR";
      const status = code === "CHANNEL_INTERNAL_AUTH_REQUIRED"
        ? 401
        : code === "CHANNEL_TRANSIENT_OFFLINE" || code === "CHANNEL_TRANSIENT_DISCONNECTED"
          ? 409
          : code === "CHANNEL_TRANSIENT_BUSY"
            ? 429
            : code === "CHANNEL_TRANSIENT_TIMEOUT"
              ? 504
              : 400;
      return json({ ok: false, code }, status);
    }
  }

  async webSocketMessage(socket, message) {
    const attachment=socket.deserializeAttachment();
    if (!attachment || attachment.superseded) return;
    // Fallback only for local test runtimes without automatic text responses.
    if(message===PROBE_REQUEST){socket.send(PROBE_RESPONSE);return;}
    let payload;
    try {
      const raw = typeof message === "string"
        ? message
        : new TextDecoder().decode(message);
      if (new TextEncoder().encode(raw).byteLength > MAX_TRANSIENT_RESULT_BYTES) {
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
      && payload.type === "LIVENESS"
      && (
        Object.keys(payload).sort().join(",") === "schema,type"
        || Object.keys(payload).sort().join(",") === "metrics,schema,type"
      )
    ) {
      const attachment = socket.deserializeAttachment();
      if (!attachment || attachment.superseded) return;
      try {
        const telemetry = Object.prototype.hasOwnProperty.call(payload, "metrics")
          ? canonicalChannelTelemetry(payload.metrics) : null;
        await refreshLiveness(
          this.env,
          attachment?.tenant_id,
          attachment?.device_id,
          telemetry,
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

    if (
      payload
      && payload.schema === EVENT_SCHEMA
      && payload.type === "CALL_RESULT"
    ) {
      try {
        const keys = Object.keys(payload).sort().join(",");
        if (keys !== "call_id,error_code,learning_signal,result,schema,state,type") {
          throw new Error("CHANNEL_TRANSIENT_RESULT_INVALID");
        }
        const callId = cleanIdentifier(payload.call_id, 180);
        const state = String(payload.state || "").trim().toUpperCase();
        if (!["COMPLETED", "FAILED"].includes(state)) {
          throw new Error("CHANNEL_TRANSIENT_RESULT_INVALID");
        }
        const signal = cleanLearningSignal(payload.learning_signal);
        const pending = this.pendingTransient.get(callId);
        if (!pending || pending.socket!==socket) return;
        this.pendingTransient.delete(callId);
        pending.resolve({
          schema: "hara.commander-transient-rpc.v1",
          ok: state === "COMPLETED",
          call_id: callId,
          state,
          result: payload.result == null ? {} : payload.result,
          error_code: state === "FAILED"
            ? cleanIdentifier(payload.error_code || "DEVICE_EXECUTION_FAILED", 120)
            : null,
          learning_signal: signal,
        });
      } catch (_error) {
        socket.close(1008, "CHANNEL_TRANSIENT_RESULT_INVALID");
      }
      return;
    }

    socket.close(1008, "CHANNEL_MESSAGE_DENIED");
  }

  async webSocketClose(socket, _code, _reason, _wasClean) {
    // Short network blips are coalesced in the per-device DO instead of
    // amplifying into an immediate OFFLINE -> ONLINE D1 write pair.
    try {
      await this.withPresence(()=>scheduleDisconnected(this.ctx, socket.deserializeAttachment()));
    } catch (_error) {
      // Presence will fail stale after the bounded Event V2 liveness window.
    }
    for (const [id,pending] of this.pendingTransient) {
      if (pending.socket===socket) {
        pending.reject(new Error("CHANNEL_TRANSIENT_DISCONNECTED"));
        this.pendingTransient.delete(id);
      }
    }
  }

  async alarm() {
    return this.withPresence(async()=>{
    const pending = await this.ctx.storage.get(PENDING_OFFLINE_KEY);
    if (!pending) return;

    const reconnected = currentSockets(this.ctx).length > 0;
    if (reconnected) {
      await this.ctx.storage.delete(PENDING_OFFLINE_KEY);
      return;
    }

    // Let an uncaught failure retry under the Durable Objects alarm contract.
    await markDisconnected(this.env, pending);
    await this.ctx.storage.delete(PENDING_OFFLINE_KEY);
    });
  }

  webSocketError(socket, _error) {
    for (const [id,pending] of this.pendingTransient) {
      if(pending.socket!==socket)continue;
      pending.reject(new Error("CHANNEL_TRANSIENT_DISCONNECTED"));
      this.pendingTransient.delete(id);
    }
    try {
      socket.close(1011, "CHANNEL_SOCKET_ERROR");
    } catch (_closeError) {
      // Connection may already be gone.
    }
  }
}
