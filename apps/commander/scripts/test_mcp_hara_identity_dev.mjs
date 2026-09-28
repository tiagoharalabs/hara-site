import assert from "node:assert/strict";
import { validateAccessTokenClaims } from "../src/oidc.js";
import {
  haraIdentityMcpDevEnabled,
  haraIdentityMcpDevProtectedResourceMetadata,
} from "../src/mcp-hara-identity-dev.mjs";

const now = 1_800_000_000;
const clientId = "dcr-client-1486";
const issuer = "https://auth.haralabs.com.br/";
const good = {
  iss: "https://auth.haralabs.com.br",
  sub: "subject-1486",
  aud: ["dcr-project", clientId, "other-dcr-client"],
  client_id: clientId,
  scope: "openid profile email",
  iat: now - 10,
  exp: now + 300,
};

assert.equal(haraIdentityMcpDevEnabled({
  ENVIRONMENT: "DEV",
  CUSTOMER_MCP_HARA_IDENTITY_AUTH: "true",
}), true);
assert.equal(haraIdentityMcpDevEnabled({
  ENVIRONMENT: "PROD",
  CUSTOMER_MCP_HARA_IDENTITY_AUTH: "true",
}), false);

const request = new Request("https://hara-commander-dev-v2.example/api/dev/mcp");
const metadata = haraIdentityMcpDevProtectedResourceMetadata(request, {
  ENVIRONMENT: "DEV",
  CUSTOMER_MCP_HARA_IDENTITY_AUTH: "true",
  AUTH_ISSUER: issuer,
});
assert.deepEqual(metadata.authorization_servers, ["https://auth.haralabs.com.br"]);
assert.equal(metadata.resource, "https://hara-commander-dev-v2.example/api/dev/mcp");
assert.deepEqual(metadata.scopes_supported, ["openid"]);

const validated = validateAccessTokenClaims({
  claims: good,
  issuer,
  clientId,
  requiredScopes: ["openid"],
  nowSeconds: now,
});
assert.equal(validated.client_binding, "client_id");
assert.equal(validated.audiences.includes(clientId), true);

for (const [mutate, code] of [
  [(c) => ({...c, iss: "https://evil.example"}), "OIDC_ACCESS_TOKEN_ISSUER_MISMATCH"],
  [(c) => ({...c, aud: ["dcr-project"]}), "OIDC_ACCESS_TOKEN_AUDIENCE_MISMATCH"],
  [(c) => ({...c, client_id: "other"}), "OIDC_ACCESS_TOKEN_CLIENT_MISMATCH"],
  [(c) => { const x={...c}; delete x.client_id; return x; }, "OIDC_ACCESS_TOKEN_CLIENT_BINDING_MISSING"],
  [(c) => ({...c, scope: "profile email"}), "OIDC_ACCESS_TOKEN_SCOPE_MISSING"],
]) {
  assert.throws(
    () => validateAccessTokenClaims({
      claims: mutate(good),
      issuer,
      clientId,
      requiredScopes: ["openid"],
      nowSeconds: now,
    }),
    new RegExp(code),
  );
}

const azp = {...good, azp: clientId};
delete azp.client_id;
assert.equal(validateAccessTokenClaims({
  claims: azp,
  issuer,
  clientId,
  requiredScopes: ["openid"],
  nowSeconds: now,
}).client_binding, "azp");

console.log("HARA_ISSUE1486_DEV_MCP_METADATA=PASS");
console.log("HARA_ISSUE1486_DCR_AUDIENCE_CLIENT_BINDING=PASS");
console.log("HARA_ISSUE1486_TOKEN_NEGATIVE_MATRIX=PASS");
console.log("HARA_ISSUE1486_PROD_GATE=DEFAULT_OFF_BY_ENV");
