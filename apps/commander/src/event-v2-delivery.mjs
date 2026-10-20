// A wake is only delivered to the current authenticated socket. The D1 call
// queue remains authoritative if every socket is stale or a send fails.
export function deliverCurrentWake(sockets, event, schema) {
  let delivered = 0;
  for (const socket of sockets) {
    if (socket.readyState !== WebSocket.OPEN) continue;
    try {
      const attachment = socket.deserializeAttachment();
      if (!attachment || attachment.schema !== schema
          || attachment.superseded !== false) continue;
      socket.send(event);
      delivered += 1;
    } catch (_error) {
      // A close may race the send; continue to another current socket.
    }
  }
  return delivered;
}
