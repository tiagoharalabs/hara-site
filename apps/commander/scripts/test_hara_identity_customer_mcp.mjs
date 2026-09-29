import assert from "node:assert/strict";

import {
  haraIdentityCustomerMcpEnabled,
  haraIdentityCustomerMcpProtectedResourceMetadata,
  haraIdentityCustomerMcpUnauthorized,
  validateOpaqueIntrospection,
  verifyHaraIdentityCustomerMcpBearer,
} from "../src/mcp-hara-identity-customer.mjs";

const env = {
  ENVIRONMENT: "PROD",
  CUSTOMER_MCP_EDGE_ENABLED: "true",
  CUSTOMER_MCP_RESOURCE: "https://commander.haralabs.com.br/api/mcp",
  AUTH_ISSUER: "https://auth.haralabs.com.br/",
};

assert.equal(haraIdentityCustomerMcpEnabled(env), true);
assert.equal(
  haraIdentityCustomerMcpEnabled({ ...env, ENVIRONMENT: "DEV" }),
  false,
);
assert.equal(
  haraIdentityCustomerMcpEnabled({ ...env, CUSTOMER_MCP_EDGE_ENABLED: "false" }),
  false,
);

const request = new Request(
  "https://commander.haralabs.com.br/.well-known/oauth-protected-resource/api/mcp",
);
const metadata = haraIdentityCustomerMcpProtectedResourceMetadata(request, env);
assert.equal(metadata.resource, "https://commander.haralabs.com.br/api/mcp");
assert.deepEqual(metadata.authorization_servers, ["https://auth.haralabs.com.br"]);
assert.deepEqual(metadata.bearer_methods_supported, ["header"]);
assert.deepEqual(metadata.scopes_supported, ["openid", "email"]);

const unauthorized = haraIdentityCustomerMcpUnauthorized(
  new Request("https://commander.haralabs.com.br/api/mcp"),
);
assert.equal(unauthorized.status, 401);
assert.match(
  unauthorized.headers.get("www-authenticate") || "",
  /resource_metadata="https:\/\/commander\.haralabs\.com\.br\/\.well-known\/oauth-protected-resource\/api\/mcp"/,
);

await assert.rejects(
  () => verifyHaraIdentityCustomerMcpBearer(
    new Request("https://commander.haralabs.com.br/api/mcp", {
      headers: { authorization: "Bearer header.payload.signature" },
    }),
    env,
  ),
  /HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISSING/,
);

console.log("COMMANDER_HARA_IDENTITY_PROD_MCP_METADATA=PASS");
console.log("COMMANDER_HARA_IDENTITY_PROD_MCP_CHALLENGE=PASS");
console.log("COMMANDER_HARA_IDENTITY_PROD_MCP_PROJECT_AUD=FAIL_CLOSED");
console.log("COMMANDER_HARA_IDENTITY_PROD_MCP_DEV_ENABLE=DENY");


const introspectionBase = {
  active: true,
  iss: "https://auth.haralabs.com.br",
  client_id: "392794504995799043",
  aud: [
    "392794504995799043",
    "391782241182810115",
    "HARA-INTROSPECTION-CLIENT",
  ],
  scope: "openid email",
  exp: 2000000000,
  iat: 1700000000,
  sub: "HARA-USER-SUBJECT",
};
const opaque = validateOpaqueIntrospection({
  payload: introspectionBase,
  issuer: "https://auth.haralabs.com.br/",
  projectAudience: "391782241182810115",
  introspectionClientId: "HARA-INTROSPECTION-CLIENT",
  userInfo: { sub: "HARA-USER-SUBJECT" },
  nowSeconds: 1950000000,
});
assert.equal(opaque.token_format, "OPAQUE");
assert.equal(opaque.client_id, "392794504995799043");
assert.equal(opaque.subject, "HARA-USER-SUBJECT");
assert.deepEqual(opaque.scopes, ["openid", "email"]);

assert.throws(
  () => validateOpaqueIntrospection({
    payload: { ...introspectionBase, active: false },
    issuer: "https://auth.haralabs.com.br/",
    projectAudience: "391782241182810115",
    introspectionClientId: "HARA-INTROSPECTION-CLIENT",
    userInfo: { sub: "HARA-USER-SUBJECT" },
  }),
  /HARA_IDENTITY_MCP_INTROSPECTION_INACTIVE/,
);
assert.throws(
  () => validateOpaqueIntrospection({
    payload: { ...introspectionBase, iss: "https://evil.example" },
    issuer: "https://auth.haralabs.com.br/",
    projectAudience: "391782241182810115",
    introspectionClientId: "HARA-INTROSPECTION-CLIENT",
    userInfo: { sub: "HARA-USER-SUBJECT" },
  }),
  /HARA_IDENTITY_MCP_INTROSPECTION_ISSUER_MISMATCH/,
);
assert.throws(
  () => validateOpaqueIntrospection({
    payload: { ...introspectionBase, aud: ["392794504995799043", "HARA-INTROSPECTION-CLIENT"] },
    issuer: "https://auth.haralabs.com.br/",
    projectAudience: "391782241182810115",
    introspectionClientId: "HARA-INTROSPECTION-CLIENT",
    userInfo: { sub: "HARA-USER-SUBJECT" },
  }),
  /HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISMATCH/,
);
assert.throws(
  () => validateOpaqueIntrospection({
    payload: { ...introspectionBase, aud: ["392794504995799043", "391782241182810115"] },
    issuer: "https://auth.haralabs.com.br/",
    projectAudience: "391782241182810115",
    introspectionClientId: "HARA-INTROSPECTION-CLIENT",
    userInfo: { sub: "HARA-USER-SUBJECT" },
  }),
  /HARA_IDENTITY_MCP_INTROSPECTION_AUD_MISMATCH/,
);
assert.throws(
  () => validateOpaqueIntrospection({
    payload: { ...introspectionBase, scope: "email" },
    issuer: "https://auth.haralabs.com.br/",
    projectAudience: "391782241182810115",
    introspectionClientId: "HARA-INTROSPECTION-CLIENT",
    userInfo: { sub: "HARA-USER-SUBJECT" },
  }),
  /HARA_IDENTITY_MCP_SCOPE_MISSING/,
);
assert.throws(
  () => validateOpaqueIntrospection({
    payload: introspectionBase,
    issuer: "https://auth.haralabs.com.br/",
    projectAudience: "391782241182810115",
    introspectionClientId: "HARA-INTROSPECTION-CLIENT",
    userInfo: { sub: "DIFFERENT-SUBJECT" },
  }),
  /HARA_IDENTITY_MCP_SUBJECT_MISMATCH/,
);

console.log("COMMANDER_HARA_IDENTITY_OPAQUE_INTROSPECTION=PASS");
console.log("COMMANDER_HARA_IDENTITY_INTROSPECTION_NEGATIVE_MATRIX=PASS");
