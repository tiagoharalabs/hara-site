#!/usr/bin/env node
// Exact Worker enrollment function and production SQL against isolated SQLite.
import assert from "node:assert/strict";
import { createHash, randomBytes, webcrypto } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import * as enrollmentSql from "../src/device-enrollment.mjs";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const worker = fs.readFileSync(path.join(APP, "src/worker.js"), "utf8");
const routeStart = worker.indexOf('if ((url.pathname === "/api/device/enroll" || url.pathname === "/api/device/enroll-intent")');
const routeEnd = worker.indexOf('if (url.pathname === "/api/device/heartbeat"', routeStart);
assert(routeStart >= 0 && routeEnd > routeStart, "versioned enrollment route missing");
const route = worker.slice(routeStart, routeEnd);
for (const required of ["enforceDeviceEnrollClientRateLimit", "enforceDeviceEnrollTokenRateLimit",
                        "DEVICE_ENROLLMENT_CLIENT_TOKEN_INVALID", "enrollDevice(env, body)"]) {
  assert(route.includes(required), `enrollment route guard missing: ${required}`);
}
console.log("DEVICE_ENROLL_INTENT_ROUTE_SHARES_RATE_LIMITS=PASS");
const start = worker.indexOf("async function enrollDevice(");
const end = worker.indexOf("\nasync function resolveDeviceCredential(", start);
assert(start >= 0 && end > start);
const now = "2026-10-20T23:30:00.000Z";
const tomorrow = "2026-10-21T23:30:00.000Z";
const hash = value => createHash("sha256").update(value).digest("base64url");
const db = new DatabaseSync(":memory:");
for (const name of fs.readdirSync(path.join(APP, "migrations")).filter(name => name.endsWith(".sql")).sort()) {
  db.exec(fs.readFileSync(path.join(APP, "migrations", name), "utf8"));
}
db.prepare("INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES ('QA_TENANT','QA only','ACTIVE','DEV',?)").run(now);
db.prepare("INSERT INTO users(subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES ('QA_OWNER','QA_TENANT','https://qa.invalid','qa','ACTIVE','OWNER',?)").run(now);
db.prepare("INSERT OR IGNORE INTO plans (plan_code,display_name,meter_id,period_kind,unit_limit,state,active_device_limit) VALUES ('FOUNDER_INTERNAL','QA Founder','HARA_COMMANDER_GOVERNED_INVOKE','NONE',NULL,'ACTIVE',NULL)").run();
db.prepare("INSERT INTO entitlements (entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc) VALUES ('QA_ENT','QA_TENANT','QA_OWNER','FOUNDER_INTERNAL','ACTIVE',?)").run(now);
const seed = label => {
  const subject = "QA_OWNER_" + label;
  db.prepare("INSERT INTO users(subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES (?,'QA_TENANT','https://qa.invalid',?,'ACTIVE','OWNER',?)")
    .run(subject, label, now);
  db.prepare("INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc) VALUES (?,?,?,?,?,?)")
    .run("PAIR_" + label, hash("QA_PAIR_" + label), "QA_TENANT", subject, now, tomorrow);
};
seed("SELECTION_FAULT");
seed("ACK_LOST");
seed("LEGACY");

let failSelection = false;
const productDb = {
  prepare(sql) {
    return { bind(...args) { return {
      async first() { return db.prepare(sql).get(...args) || null; },
      async run() {
        if (failSelection && sql.includes("INSERT OR IGNORE INTO commander_device_selections")) {
          throw new Error("QA_SELECTION_WRITE_UNAVAILABLE");
        }
        const result = db.prepare(sql).run(...args);
        return { meta: { changes: Number(result.changes) } };
      },
    }; } };
  },
  async batch(statements) {
    db.exec("BEGIN IMMEDIATE");
    try {
      const results = [];
      for (const statement of statements) results.push(await statement.run());
      db.exec("COMMIT");
      return results;
    } catch (error) {
      db.exec("ROLLBACK");
      throw error;
    }
  },
};
const context = vm.createContext({
  ...enrollmentSql,
  cleanOpaque: value => String(value),
  sha256: async value => hash(String(value)),
  cleanDeviceName: value => String(value),
  normalizeDevicePlatform: value => String(value),
  cleanAgentValue: value => String(value || ""),
  normalizeApprovalMode: value => String(value || "ASK_EVERY_ACTION"),
  crypto: webcrypto,
  randomToken: () => randomBytes(48).toString("base64url"),
  nowIso: () => now,
});
vm.runInContext(worker.slice(start, end) + "\nglobalThis.testEnroll = enrollDevice;", context);
const count = () => Number(db.prepare("SELECT COUNT(*) AS n FROM commander_devices WHERE state='ACTIVE'").get().n);
const consumed = label => Boolean(db.prepare("SELECT consumed_at_utc FROM device_pairing_tokens WHERE pairing_id=?")
  .get("PAIR_" + label).consumed_at_utc);
const enroll = (label, secret) => context.testEnroll({ PRODUCT_DB: productDb }, {
  pairing_token: "QA_PAIR_" + label,
  client_device_token: secret,
  device_name: "QA_HOST", platform: "LINUX", architecture: "x86_64",
  agent_version: "0.3.43", approval_mode: "ASK_EVERY_ACTION",
});

try {
  const selectedSecret = randomBytes(48).toString("base64url");
  failSelection = true;
  await assert.rejects(enroll("SELECTION_FAULT", selectedSecret));
  assert.equal(count(), 0, "selection error must roll back registration");
  assert.equal(consumed("SELECTION_FAULT"), false, "selection error must not consume pairing");
  failSelection = false;
  const afterFault = await enroll("SELECTION_FAULT", selectedSecret);
  assert.equal(afterFault.device_token, selectedSecret);
  assert.equal(count(), 1);
  console.log("DEVICE_ENROLL_SELECTION_FAULT_TRANSACTIONAL=PASS");

  const secret = randomBytes(48).toString("base64url");
  const responseLost = await enroll("ACK_LOST", secret);
  assert.equal(responseLost.device_token, secret);
  const recovered = await enroll("ACK_LOST", secret);
  assert.equal(recovered.device_id, responseLost.device_id);
  assert.equal(recovered.device_token, secret);
  assert.equal(recovered.enrolled_at_utc, responseLost.enrolled_at_utc);
  assert.equal(count(), 2);
  await assert.rejects(enroll("ACK_LOST", randomBytes(48).toString("base64url")),
                       /DEVICE_PAIRING_INVALID/);
  console.log("DEVICE_ENROLL_LOST_ACK_RECOVERY_AUTHENTICATED=PASS");

  const legacy = await enroll("LEGACY", undefined);
  assert(legacy.device_token && legacy.device_id.startsWith("HARA-DEVICE-"));
  assert.equal(count(), 3);
  console.log("DEVICE_ENROLL_LEGACY_CLIENT_COMPATIBILITY=PASS");
} finally {
  db.close();
}
