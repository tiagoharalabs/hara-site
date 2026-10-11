// Adaptive bounded status reads for already-accepted customer calls.
// Long commands should not hammer D1 at a fixed 250ms cadence.
export const CUSTOMER_STATUS_TIMEOUT_MS = 45_000;

export function customerStatusWaitMs(retryAfterMs, elapsedMs, remainingMs) {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) throw new Error("STATUS_POLL_ELAPSED_INVALID");
  if (!Number.isFinite(remainingMs) || remainingMs <= 0) throw new Error("STATUS_POLL_DEADLINE");
  const hint = Number.isFinite(retryAfterMs) && retryAfterMs > 0
    ? Math.max(100, Math.min(3000, retryAfterMs))
    : 250;
  const tier = elapsedMs < 1500 ? 250
    : elapsedMs < 5000 ? 500
    : elapsedMs < 15000 ? 1000
    : elapsedMs < 30000 ? 2000
    : 3000;
  return Math.max(1, Math.min(remainingMs, Math.max(tier, hint)));
}
