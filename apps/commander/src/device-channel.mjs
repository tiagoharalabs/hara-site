import { DurableObject } from "cloudflare:workers";
import { canonicalChannelTelemetry, telemetryRollupQuery } from "./device-telemetry.mjs";
import { observeEventV2ChannelLoss, observeEventV2ChannelRecovery } from './recovery-alerts.mjs';

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
const COMMERCIAL_CONTRACT = 'commercial-0.3.56-durable-dev.v1';
const COMMERCIAL_STALE_MS = 120000;
const COMMERCIAL_INCIDENT_KEY = 'commercial_recovery_incident';

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
  const result = await env.PRODUCT_DB.prepare(
    `UPDATE commander_devices
        SET tunnel_mode = 'EVENT_V2_OFFLINE', last_seen_at_utc = ?
      WHERE tenant_id = ?
        AND device_id = ?
        AND tunnel_mode = 'EVENT_V2'
        AND state = 'ACTIVE'
        AND revoked_at_utc IS NULL`
  ).bind(seenAt, tenantId, deviceId).run();
  return {seen_at_utc:seenAt, changed:Boolean(result.meta?.changes)};
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
    ...(attachment.event_v2_contract === COMMERCIAL_CONTRACT ? {
      event_v2_contract: COMMERCIAL_CONTRACT,
      connected_at_ms: attachment.connected_at_ms,
      probe_anchor_ms: attachment.probe_anchor_ms,
    } : {}),
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
        const commercialContract = request.headers.get('x-hara-event-v2-contract');
        if (commercialContract !== null
            && (commercialContract !== 'commercial-0.3.56-durable-dev.v1'
                || this.env.ENVIRONMENT !== 'DEV'
                || this.env.DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED !== 'true')) {
          throw new Error('CHANNEL_CONTRACT_NOT_ADMITTED');
        }
        if (commercialContract !== null
            && (typeof this.ctx.getWebSocketAutoResponseTimestamp !== 'function'
                || this.env.COMMANDER_RECOVERY_ALERTS_ENABLED !== 'true')) {
          throw new Error('CHANNEL_COMMERCIAL_DETECTOR_REQUIRED');
        }

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
          event_v2_contract: commercialContract,
          connected_at_ms: Date.now(),
        });
        this.ctx.acceptWebSocket(server, [
          "tenant:" + tenantId,
          "device:" + deviceId,
        ]);
        if (commercialContract) await this.ctx.storage.setAlarm(Date.now() + COMMERCIAL_STALE_MS);

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
        if (attachment.event_v2_contract != null) throw new Error('CHANNEL_TRANSIENT_NOT_ADMITTED');
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
          event_v2_contract: currentSockets(this.ctx)[0]?.deserializeAttachment()?.event_v2_contract ?? null,
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
      await this.withPresence(()=>{
        const attachment = socket.deserializeAttachment();
        if (attachment?.event_v2_contract === COMMERCIAL_CONTRACT) {
          attachment.probe_anchor_ms = this.commercialProbeAnchor(socket);
        }
        return scheduleDisconnected(this.ctx, attachment);
      });
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
    const commercial = currentSockets(this.ctx).find(socket =>
      socket.deserializeAttachment()?.event_v2_contract === COMMERCIAL_CONTRACT);
    if (commercial && this.commercialDetectorEnabled()) {
      await this.observeCommercialChannel(commercial);
      return;
    }
    if (!pending) return;

    const reconnected = currentSockets(this.ctx).length > 0;
    if (reconnected) {
      await this.ctx.storage.delete(PENDING_OFFLINE_KEY);
      return;
    }

    // Let an uncaught failure retry under the Durable Objects alarm contract.
    if (pending.event_v2_contract === COMMERCIAL_CONTRACT && this.commercialDetectorEnabled()) {
      await this.recordCommercialLoss(pending, 'EVENT_V2_CHANNEL_CLOSED');
    }
    await markDisconnected(this.env, pending);
    await this.ctx.storage.delete(PENDING_OFFLINE_KEY);
    });
  }

  commercialDetectorEnabled() {
    return this.env.ENVIRONMENT === 'DEV'
      && this.env.DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED === 'true'
      && this.env.COMMANDER_RECOVERY_ALERTS_ENABLED === 'true';
  }

  commercialProbeAnchor(socket) {
    const connected = socket.deserializeAttachment()?.connected_at_ms;
    const timestamp = this.ctx.getWebSocketAutoResponseTimestamp(socket);
    const probe = timestamp === null ? connected : Number(timestamp);
    if (!Number.isSafeInteger(connected) || !Number.isSafeInteger(probe)
        || connected < 0 || probe < 0 || Math.max(connected, probe) > Date.now()) {
      throw new Error('CHANNEL_PROBE_TIMESTAMP_INVALID');
    }
    return Math.max(connected, probe);
  }

  async commercialDevice(attachment) {
    return this.env.PRODUCT_DB.prepare(
      'SELECT device_id,tenant_id,state,revoked_at_utc,approval_mode,tunnel_mode,last_seen_at_utc '+
      'FROM commander_devices WHERE tenant_id=? AND device_id=?'
    ).bind(attachment.tenant_id,attachment.device_id).first();
  }

  commercialLive(device) {
    return device?.state === 'ACTIVE' && !device.revoked_at_utc && device.tunnel_mode === 'EVENT_V2';
  }

  endCommercialAuthorization(socket, attachment) {
    socket.serializeAttachment({...attachment, superseded:true});
    socket.close(4003, 'CHANNEL_AUTHORIZATION_ENDED');
  }

  async recoverCommercialChannel(socket, attachment, device, incident, anchor) {
    let recovered;
    try { recovered = await observeEventV2ChannelRecovery(this.env, device, incident); }
    catch (error) {
      if (!['DEVICE_AUTH_INVALID','RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER'].includes(error?.message)) throw error;
      if (this.commercialLive(await this.commercialDevice(attachment))) throw error;
      this.endCommercialAuthorization(socket, attachment);
      return;
    }
    // A successful INSERT or replay is historical persistence, not a lease to
    // override a manual stop committed while that write was awaiting I/O.
    if (!this.commercialLive(await this.commercialDevice(attachment))) {
      this.endCommercialAuthorization(socket, attachment);
      return;
    }
    if (recovered) await this.ctx.storage.delete(COMMERCIAL_INCIDENT_KEY);
    await this.ctx.storage.setAlarm(anchor + COMMERCIAL_STALE_MS);
  }

  async recordCommercialLoss(attachment, code) {
    let incident = await this.ctx.storage.get(COMMERCIAL_INCIDENT_KEY);
    if (incident) return incident;
    const device = await this.commercialDevice(attachment);
    if (!device || device.state !== 'ACTIVE' || device.revoked_at_utc
        || device.tunnel_mode !== 'EVENT_V2' || device.approval_mode !== 'PERSISTENT_TRUSTED') return null;
    const anchor = attachment.probe_anchor_ms ?? attachment.connected_at_ms;
    try {
      incident = await observeEventV2ChannelLoss(this.env, device, {
        probe_anchor_ms: anchor,
        at_ms: code === 'EVENT_V2_PROBE_STALE' ? anchor + COMMERCIAL_STALE_MS : attachment.scheduled_at_ms,
        error_code: code,
      });
    } catch (error) {
      if (!['DEVICE_AUTH_INVALID','RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER'].includes(error?.message)) throw error;
      const current = await this.commercialDevice(attachment);
      if (current?.state === 'ACTIVE' && !current.revoked_at_utc && current.tunnel_mode === 'EVENT_V2') throw error;
      return null; // a live lifecycle change is a stop, not an incident/retry loop
    }
    if (incident) await this.ctx.storage.put(COMMERCIAL_INCIDENT_KEY, incident);
    return incident;
  }

  async observeCommercialChannel(socket) {
    const attachment = socket.deserializeAttachment();
    const anchor = this.commercialProbeAnchor(socket);
    // Even a fresh transport probe cannot extend a revoked enrollment or a
    // manual stop when the best-effort invalidation RPC was lost.
    if (!this.commercialLive(await this.commercialDevice(attachment))) {
      this.endCommercialAuthorization(socket, attachment);
      return;
    }
    let incident = await this.ctx.storage.get(COMMERCIAL_INCIDENT_KEY);
    if (!incident && Date.now() - anchor < COMMERCIAL_STALE_MS) {
      // Native auto-response timestamps, not OPEN/PING/PID, prove traffic.
      // A healthy alarm reads lifecycle only; it performs no D1 writes.
      await this.ctx.storage.setAlarm(anchor + COMMERCIAL_STALE_MS);
      return;
    }
    if (!incident) incident = await this.recordCommercialLoss({...attachment, probe_anchor_ms:anchor}, 'EVENT_V2_PROBE_STALE');
    const device = await this.commercialDevice(attachment);
    if (!this.commercialLive(device)) {
      this.endCommercialAuthorization(socket, attachment);
      return;
    }
    // Auto-responses can arrive while D1 persistence is awaiting I/O. Recheck
    // after that boundary before changing presence or closing a healthy peer.
    const latest = this.commercialProbeAnchor(socket);
    const probe = this.ctx.getWebSocketAutoResponseTimestamp(socket);
    if (incident && probe !== null && Number(probe) >= attachment.connected_at_ms
        && latest > incident.probe_anchor_ms && Date.now() - latest < COMMERCIAL_STALE_MS) {
      await this.recoverCommercialChannel(socket, attachment, device, incident, latest);
      return;
    }
    if (Date.now() - latest < COMMERCIAL_STALE_MS) {
      await this.ctx.storage.setAlarm(latest + COMMERCIAL_STALE_MS);
      return;
    }
    const transition = await markDisconnected(this.env, attachment);
    const afterWrite = this.commercialProbeAnchor(socket);
    if (transition?.changed && afterWrite > latest && Date.now() - afterWrite < COMMERCIAL_STALE_MS) {
      // Only undo our automatic presence transition. The canonical manual
      // stop uses OUTBOUND_RELAY_OFFLINE, which this CAS cannot overwrite,
      // even when it shares the exact timestamp with our write.
      const restored = await this.env.PRODUCT_DB.prepare(
        "UPDATE commander_devices SET tunnel_mode='EVENT_V2' WHERE tenant_id=? AND device_id=? "+
        "AND state='ACTIVE' AND revoked_at_utc IS NULL AND tunnel_mode='EVENT_V2_OFFLINE' AND last_seen_at_utc=?"
      ).bind(attachment.tenant_id,attachment.device_id,transition.seen_at_utc).run();
      if (restored.meta?.changes) {
        const current = await this.commercialDevice(attachment);
        if (incident && current?.state === 'ACTIVE' && !current.revoked_at_utc && current.tunnel_mode === 'EVENT_V2') {
          await this.recoverCommercialChannel(socket, attachment, current, incident, afterWrite);
          return;
        }
      }
    }
    socket.serializeAttachment({...attachment, superseded:true});
    socket.close(4002, 'CHANNEL_PROBE_STALE');
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
