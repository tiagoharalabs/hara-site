import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";

const source = fs.readFileSync(new URL("../src/worker.js", import.meta.url), "utf8");
function extract(name) {
  const match = new RegExp(`(?:async )?function ${name}\\(`).exec(source);
  assert.ok(match, name);
  const end = source.indexOf("\n}", match.index);
  assert.ok(end > match.index, name);
  return source.slice(match.index, end + 2);
}
const now = new Date();
const future = new Date(now.getTime() + 60_000).toISOString();
const past = new Date(now.getTime() - 60_000).toISOString();
const db = new DatabaseSync(":memory:");
db.exec(`
  CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY,display_name TEXT,state TEXT);
  CREATE TABLE plans (plan_code TEXT PRIMARY KEY,display_name TEXT,meter_id TEXT,period_kind TEXT,unit_limit INTEGER,state TEXT);
  CREATE TABLE entitlements (entitlement_id TEXT PRIMARY KEY,tenant_id TEXT,subject_id TEXT,plan_code TEXT,state TEXT,valid_from_utc TEXT,valid_until_utc TEXT);
  INSERT INTO tenants VALUES ('T','Tenant','ACTIVE');
  INSERT INTO plans VALUES ('STANDARD','HARA Commander','HARA_COMMANDER_GOVERNED_INVOKE','CALENDAR_MONTH',1000000,'ACTIVE');
`);
const env = { PRODUCT_DB: { prepare(sql) {
  const stmt = db.prepare(sql);
  return { bind(...args) { return { async first() { return stmt.get(...args) || null; } }; } };
} } };
const resolver = new Function("nowIso", `return (${extract("entitlementForTenant")})`)(() => new Date().toISOString());
const setEntitlement = (from, until) => db.prepare(`INSERT INTO entitlements VALUES ('BILLING:T','T',NULL,'STANDARD','ACTIVE',?,?)
  ON CONFLICT(entitlement_id) DO UPDATE SET valid_from_utc=excluded.valid_from_utc,valid_until_utc=excluded.valid_until_utc`).run(from, until);
setEntitlement(past, past);
assert.equal(await resolver(env, "T"), null, "expired paid access must not resolve");
setEntitlement(future, null);
assert.equal(await resolver(env, "T"), null, "future paid access must not resolve");
setEntitlement(past, future);
const active = await resolver(env, "T");
assert.equal(active.valid_until_utc, future);
db.exec(`
  INSERT INTO plans VALUES ('FOUNDER_INTERNAL','Founder/Internal','HARA_COMMANDER_GOVERNED_INVOKE','NONE',NULL,'ACTIVE');
  INSERT INTO entitlements VALUES ('FOUNDER:T','T',NULL,'FOUNDER_INTERNAL','ACTIVE','2026-01-01T00:00:00Z',NULL);
`);
assert.equal((await resolver(env,"T")).plan_code,"FOUNDER_INTERNAL",
  "Founder must win entitlement selection if a historical paid row also exists");
assert.ok(source.includes("valid_until_utc: entitlement.valid_until_utc"), "lease caller must pass the paid deadline");
assert.ok(extract("dashboardForSubject").includes("e.valid_until_utc > ?"), "portal must reject expired entitlements");
assert.ok(extract("dashboardForSubject").includes("p.plan_code = 'FOUNDER_INTERNAL'"),
  "portal must select Founder before a historical paid row");
console.log("BILLING_EXPIRED_AND_FUTURE_ENTITLEMENTS=DENIED");

const lease = new Function(
  "PRODUCT_LEASE_TTL_SECONDS", "monthKey", "monthEndUtc", "localBudgetEligibleDevice", "crypto",
  `return (${extract("productLeaseForContext")})`,
)(21600,
  date => date.toISOString().slice(0, 7),
  period => { const [year, month] = period.split("-").map(Number); return new Date(Date.UTC(year, month, 1)).toISOString(); },
  () => false,
  crypto,
);
const context = {
  tenant_id: "T", entitlement_id: "BILLING:T", plan_code: "STANDARD",
  plan_name: "HARA Commander", meter_id: "HARA_COMMANDER_GOVERNED_INVOKE",
  period_kind: "CALENDAR_MONTH", unit_limit: 1_000_000, valid_until_utc: future,
};
const issued = lease(context, { device_id: "D", platform: "LINUX" }, [], now);
assert.ok(Date.parse(issued.valid_until_utc) <= Date.parse(future));
assert.throws(() => lease({ ...context, valid_until_utc: past }, { device_id: "D" }, [], now), /ENTITLEMENT_NOT_ACTIVE/);
console.log("BILLING_LOCAL_LEASE_CAPPED_AT_PAID_DEADLINE=PASS");
db.close();
