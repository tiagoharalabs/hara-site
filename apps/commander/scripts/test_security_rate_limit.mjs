import assert from "node:assert/strict";
import {
  enforceLayeredRateLimit,
  enforceRateLimit,
  fixedWindowDecision,
  rateLimitActorKey,
  rateLimitClientKey,
  rateLimitSecretKey,
} from "../src/security-rate-limit.mjs";

const reqA = new Request("https://commander.example/auth/login", {
  headers: { "cf-connecting-ip": "203.0.113.7" },
});
const reqB = new Request("https://commander.example/auth/login", {
  headers: { "cf-connecting-ip": "203.0.113.8" },
});

const keyA1 = await rateLimitClientKey(reqA, "auth-login");
const keyA2 = await rateLimitClientKey(reqA, "auth-login");
const keyB = await rateLimitClientKey(reqB, "auth-login");
assert.equal(keyA1, keyA2);
assert.notEqual(keyA1, keyB);
assert(!keyA1.includes("203.0.113.7"));

const secret = "PAIRING-SECRET-MUST-NOT-APPEAR";
const secretKey = await rateLimitSecretKey("device-enroll-token", secret);
assert(!secretKey.includes(secret));

const actorKey = await rateLimitActorKey("portal-mutation", "TENANT-A", "SUBJECT-A");
assert(!actorKey.includes("TENANT-A"));
assert(!actorKey.includes("SUBJECT-A"));

await enforceRateLimit({ limit: async () => ({ success: true }) }, "k", "DENIED");
await assert.rejects(enforceRateLimit(null, "k", "DENIED"), /RATE_LIMIT_BINDING_MISSING/);
await assert.rejects(
  enforceRateLimit({ limit: async () => { throw new Error("down"); } }, "k", "DENIED"),
  /RATE_LIMIT_CHECK_FAILED/
);
await assert.rejects(
  enforceRateLimit({ limit: async () => ({ success: false }) }, "k", "TEST_RATE_LIMITED"),
  /TEST_RATE_LIMITED/
);

assert.deepEqual(
  fixedWindowDecision(null, 2, 60000, 1000),
  { success: true, window_start_ms: 1000, count: 1, retry_after_ms: 0 },
);
assert.deepEqual(
  fixedWindowDecision({ window_start_ms: 1000, count: 1 }, 2, 60000, 2000),
  { success: true, window_start_ms: 1000, count: 2, retry_after_ms: 0 },
);
assert.deepEqual(
  fixedWindowDecision({ window_start_ms: 1000, count: 2 }, 2, 60000, 3000),
  { success: false, window_start_ms: 1000, count: 2, retry_after_ms: 58000 },
);
assert.deepEqual(
  fixedWindowDecision({ window_start_ms: 1000, count: 2 }, 2, 60000, 61000),
  { success: true, window_start_ms: 61000, count: 1, retry_after_ms: 0 },
);

let fastCalls = 0;
let strictCalls = 0;
const fast = { limit: async () => { fastCalls += 1; return { success: true }; } };
const strict = {
  idFromName: (key) => `strict:${key}`,
  get: (id) => ({
    limit: async (limit, periodSeconds) => {
      strictCalls += 1;
      assert.equal(id, "strict:k");
      assert.equal(limit, 30);
      assert.equal(periodSeconds, 60);
      return { success: true };
    },
  }),
};
await enforceLayeredRateLimit(fast, strict, "k", 30, 60, "DENIED");
assert.equal(fastCalls, 1);
assert.equal(strictCalls, 1);

await assert.rejects(
  enforceLayeredRateLimit(fast, null, "k", 30, 60, "DENIED"),
  /STRICT_RATE_LIMIT_BINDING_MISSING/,
);
await assert.rejects(
  enforceLayeredRateLimit(
    fast,
    { idFromName: () => "id", get: () => ({ limit: async () => { throw new Error("down"); } }) },
    "k", 30, 60, "DENIED",
  ),
  /STRICT_RATE_LIMIT_CHECK_FAILED/,
);
await assert.rejects(
  enforceLayeredRateLimit(
    fast,
    { idFromName: () => "id", get: () => ({ limit: async () => ({ success: false }) }) },
    "k", 30, 60, "STRICT_DENIED",
  ),
  /STRICT_DENIED/,
);

const strictDown = {
  idFromName: () => "id",
  get: () => ({ limit: async () => { throw new Error("down"); } }),
};
const degraded = await enforceLayeredRateLimit(
  fast,
  strictDown,
  "k", 30, 60, "DENIED",
  { allowStrictUnavailableFallback: true },
);
assert.equal(degraded.success, true);
assert.equal(degraded.degraded, true);
assert.equal(degraded.enforcement, "FAST_BINDING_ONLY");

await assert.rejects(
  enforceLayeredRateLimit(
    { limit: async () => { throw new Error("fast-down"); } },
    strictDown,
    "k", 30, 60, "DENIED",
    { allowStrictUnavailableFallback: true },
  ),
  /RATE_LIMIT_CHECK_FAILED/,
);

console.log("COMMANDER_RATE_LIMIT_KEY_PRIVACY=PASS");
console.log("COMMANDER_RATE_LIMIT_FIXED_WINDOW=PASS");
console.log("COMMANDER_RATE_LIMIT_LAYERED_ENFORCEMENT=PASS");
console.log("COMMANDER_RATE_LIMIT_STRICT_OUTAGE_FALLBACK=FAST_LAYER_ONLY");
console.log("COMMANDER_RATE_LIMIT_FAST_LAYER_FAIL_CLOSED=PASS");
console.log("COMMANDER_RATE_LIMIT_FAIL_CLOSED=PASS");
