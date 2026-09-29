import assert from "node:assert/strict";

import {
  haraIdentityCustomerMcpEnabled,
  haraIdentityCustomerMcpProtectedResourceMetadata,
  haraIdentityCustomerMcpUnauthorized,
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
