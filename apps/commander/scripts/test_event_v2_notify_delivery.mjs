import assert from "node:assert/strict";
import { deliverCurrentWake } from "../src/event-v2-delivery.mjs";

globalThis.WebSocket = { OPEN: 1 };
const schema = "hara.commander-device-channel.v2";
const event = JSON.stringify({ schema: "hara.commander-device-event.v2", type: "CALL_AVAILABLE", call_id: "C1" });
const sent = [];
const socket = (attachment, options = {}) => ({
  readyState: options.closed ? 3 : WebSocket.OPEN,
  deserializeAttachment() {
    if (options.badAttachment) throw Error("ATTACHMENT_UNAVAILABLE");
    return attachment;
  },
  send(payload) {
    if (options.sendFails) throw Error("SOCKET_CLOSED_DURING_SEND");
    sent.push(payload);
  },
});
const current = { schema, superseded: false };
const sockets = [
  socket(current, { closed: true }),
  socket({ schema, superseded: true }),
  socket({ schema: "unknown", superseded: false }),
  socket(null),
  socket(current, { badAttachment: true }),
  socket(current, { sendFails: true }),
  socket(current),
];
assert.equal(deliverCurrentWake(sockets, event, schema), 1);
assert.deepEqual(sent, [event]);
assert.equal(deliverCurrentWake(sockets.slice(0, -1), event, schema), 0);
assert.deepEqual(sent, [event]);
console.log("EVENT_V2_STALE_REPLACED_SOCKET_WAKE=DENIED");
console.log("EVENT_V2_LIVE_SOCKET_AFTER_FAILED_SEND=DELIVERED");
console.log("EVENT_V2_ZERO_SOCKET_DELIVERY=REPORTED");
