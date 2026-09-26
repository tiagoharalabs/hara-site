import assert from "node:assert/strict";
import {
  enforceRateLimit,
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

await assert.rejects(
  enforceRateLimit(null, "k", "DENIED"),
  /RATE_LIMIT_BINDING_MISSING/
);
await assert.rejects(
  enforceRateLimit({ limit: async () => { throw new Error("down"); } }, "k", "DENIED"),
  /RATE_LIMIT_CHECK_FAILED/
);
await assert.rejects(
  enforceRateLimit({ limit: async () => ({ success: false }) }, "k", "TEST_RATE_LIMITED"),
  /TEST_RATE_LIMITED/
);

console.log("COMMANDER_RATE_LIMIT_KEY_PRIVACY=PASS");
console.log("COMMANDER_RATE_LIMIT_FAIL_CLOSED=PASS");
