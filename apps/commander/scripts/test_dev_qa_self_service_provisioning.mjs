import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { DatabaseSync } from "node:sqlite";
import { sha256, normalizeIssuer } from "../src/oidc.js";

const authUrl = new URL("../src/auth.js", import.meta.url).href;
registerHooks({
  load(url, context, nextLoad) {
    const loaded = nextLoad(url, context);
    if (url !== authUrl) return loaded;
    const source = typeof loaded.source === "string" ? loaded.source : Buffer.from(loaded.source).toString();
    // Expose the original private function only in this test loader.
    return { ...loaded, source: source + "\nexport { provisionProductionIdentity };\n" };
  },
});
const { selfServiceIdentityEnvironment, provisionProductionIdentity } = await import("../src/auth.js");
const issuer = normalizeIssuer("https://auth.haralabs.com.br/");
const qa = "394861028946477060";
const other = "394861028946477061";
const dev = {
  ENVIRONMENT: "DEV",
  CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "true",
  DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: qa,
};
let checks = 0;
function equal(actual, expected) { assert.deepEqual(actual, expected); checks += 1; }

function database() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(`
CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY,display_name TEXT,state TEXT,environment TEXT CHECK(environment IN ('DEV','REVIEW','PRODUCTION')),created_at_utc TEXT);
CREATE TABLE users (subject_id TEXT PRIMARY KEY,tenant_id TEXT,oidc_issuer TEXT,oidc_subject TEXT,email TEXT,display_name TEXT,state TEXT,role TEXT,created_at_utc TEXT,UNIQUE(oidc_issuer,oidc_subject));
CREATE TABLE identity_bindings (identity_binding_id TEXT PRIMARY KEY,subject_id TEXT,provider_code TEXT,issuer TEXT,external_subject TEXT,state TEXT,created_at_utc TEXT,revoked_at_utc TEXT,UNIQUE(issuer,external_subject));
CREATE TABLE entitlements (entitlement_id TEXT PRIMARY KEY,tenant_id TEXT,subject_id TEXT,plan_code TEXT,state TEXT,valid_from_utc TEXT,valid_until_utc TEXT);
`);
  const adapter = {
    prepare(sql) {
      const bound = {
        values: [],
        bind(...values) { this.values = values; return this; },
        async first() { return sqlite.prepare(sql).get(...this.values) || null; },
        async run() { return sqlite.prepare(sql).run(...this.values); },
      };
      return bound;
    },
    async batch(statements) {
      sqlite.exec("BEGIN");
      try {
        for (const statement of statements) await statement.run();
        sqlite.exec("COMMIT");
      } catch (error) {
        sqlite.exec("ROLLBACK"); throw error;
      }
    },
  };
  return { sqlite, adapter };
}

for (const [env, subject] of [
  [{ ...dev, CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "false" }, qa],
  [{ ...dev, CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: undefined }, qa],
  [{ ...dev, DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: "" }, qa],
  [dev, other],
  [{ ...dev, DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: "*" }, qa],
  [{ ...dev, DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: qa + ",2,3" }, qa],
  [{ ...dev, DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: qa + ",not-a-zitadel-id" }, qa],
  [{ ...dev, ENVIRONMENT: "REVIEW" }, qa],
]) {
  equal(selfServiceIdentityEnvironment(env, subject), null);
  const db = database();
  const result = await provisionProductionIdentity(
    { ...env, PRODUCT_DB: db.adapter }, { name: "QA" }, issuer, subject, "qa@example.invalid",
  );
  equal(result, null);
  equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM tenants").get().n, 0);
  db.sqlite.close();
}

const db = database();
const sameFingerprint = await sha256(issuer + "\n" + qa);
const accepted = { ...dev, PRODUCT_DB: db.adapter, FOUNDER_INTERNAL_IDENTITY_FINGERPRINT: sameFingerprint };
const first = await provisionProductionIdentity(accepted, { name: "QA" }, issuer, qa, "qa@example.invalid");
equal(first.oidc_subject, qa);
equal(db.sqlite.prepare("SELECT environment FROM tenants").get().environment, "DEV");
equal(db.sqlite.prepare("SELECT plan_code FROM entitlements").get().plan_code, "TRIAL");
equal(db.sqlite.prepare("SELECT entitlement_id FROM entitlements").get().entitlement_id, "HARA-ENTITLEMENT-" + sameFingerprint);
const again = await provisionProductionIdentity(accepted, { name: "QA" }, issuer, qa, "qa@example.invalid");
equal(again.subject_id, first.subject_id);
equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM tenants").get().n, 1);
equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM identity_bindings").get().n, 1);
equal(db.sqlite.prepare("SELECT COUNT(*) AS n FROM entitlements").get().n, 1);
db.sqlite.close();

for (const founder of [false, true]) {
  const db = database();
  const env = {
    ENVIRONMENT: "PROD",
    PRODUCT_DB: db.adapter,
    CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "false",
    DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: "",
    FOUNDER_INTERNAL_IDENTITY_FINGERPRINT: founder ? sameFingerprint : "",
  };
  const user = await provisionProductionIdentity(env, { name: "QA" }, issuer, qa, "qa@example.invalid");
  equal(user.oidc_subject, qa);
  equal(db.sqlite.prepare("SELECT environment FROM tenants").get().environment, "PRODUCTION");
  equal(db.sqlite.prepare("SELECT plan_code FROM entitlements").get().plan_code, founder ? "FOUNDER_INTERNAL" : "TRIAL");
  db.sqlite.close();
}
equal(selfServiceIdentityEnvironment({ ...dev, DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS: qa + "," + other }, other), "DEV");

const pairDb = database();
const pairEnv = { ENVIRONMENT: "PROD", PRODUCT_DB: pairDb.adapter };
for (const subject of [qa, other]) {
  await provisionProductionIdentity(pairEnv, { name: "QA" }, issuer, subject, "qa@example.invalid");
  await provisionProductionIdentity(pairEnv, { name: "QA" }, issuer, subject, "qa@example.invalid");
}
equal(pairDb.sqlite.prepare("SELECT COUNT(*) AS n FROM entitlements").get().n, 2);
equal(pairDb.sqlite.prepare("SELECT COUNT(DISTINCT tenant_id) AS n FROM entitlements").get().n, 2);
for (const subject of [qa, other]) {
  const hash = await sha256(issuer + "\n" + subject);
  equal(pairDb.sqlite.prepare("SELECT e.entitlement_id AS id FROM entitlements e JOIN users u ON u.subject_id=e.subject_id WHERE u.oidc_subject=?").get(subject).id, "HARA-ENTITLEMENT-" + hash);
}
pairDb.sqlite.close();
console.log("COMMANDER_ENTITLEMENT_FULL_HASH_AND_TWO_TENANT_IDEMPOTENCY=PASS");

console.log("COMMANDER_DEV_QA_SELF_SERVICE_ALLOWLIST=PASS");
console.log("COMMANDER_DEV_QA_SELF_SERVICE_UNLISTED_AND_MALFORMED=DENY");
console.log("COMMANDER_DEV_QA_SELF_SERVICE_MAX_SUBJECTS=2");
console.log("COMMANDER_DEV_QA_SELF_SERVICE_REAL_SQLITE_INSERT=PASS");
console.log("COMMANDER_DEV_QA_SELF_SERVICE_NO_FOUNDER_PROMOTION=PASS");
console.log("COMMANDER_PROD_SELF_SERVICE_FOUNDER_AND_TRIAL_UNCHANGED=PASS");
console.log("COMMANDER_DEV_QA_SELF_SERVICE_CHECKS=" + checks);
