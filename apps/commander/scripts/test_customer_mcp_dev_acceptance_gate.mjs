import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import {
  haraIdentityCustomerMcpEnabled,
  haraIdentityCustomerMcpAllowedHosts,
  haraIdentityCustomerMcpProtectedResourceMetadata,
} from "../src/mcp-hara-identity-customer.mjs";

// Only the runtime DurableObject base is stubbed. Requests below execute the
// actual Worker.fetch and actual customer bearer guard without network access.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "cloudflare:workers") {
      return {
        url: "data:text/javascript," + encodeURIComponent("export class DurableObject { constructor(ctx,env) { this.ctx=ctx; this.env=env; } }"),
        shortCircuit: true,
      };
    }
    return nextResolve(specifier, context);
  },
});
const { default: worker } = await import("../src/worker.js");
const host = "hara-commander-dev-v2.tiago-sartori.workers.dev";
const dev = {
  ENVIRONMENT: "DEV",
  CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "true",
  AUTH_ISSUER: "https://auth.haralabs.com.br/",
  HARA_IDENTITY_MCP_DCR_PROJECT_AUD: "QA_PUBLIC_PROJECT_AUDIENCE",
};
const prod = {
  ENVIRONMENT: "PROD",
  CUSTOMER_MCP_EDGE_ENABLED: "true",
  AUTH_ISSUER: dev.AUTH_ISSUER,
  HARA_IDENTITY_MCP_DCR_PROJECT_AUD: dev.HARA_IDENTITY_MCP_DCR_PROJECT_AUD,
};
let checks = 0;
function equal(actual, expected) { assert.deepEqual(actual, expected); checks += 1; }
equal(haraIdentityCustomerMcpEnabled(dev), true);
equal(haraIdentityCustomerMcpEnabled({ ...dev, CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "false" }), false);
equal(haraIdentityCustomerMcpEnabled({ ...dev, CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: undefined }), false);
equal(haraIdentityCustomerMcpEnabled({ ...dev, ENVIRONMENT: "REVIEW" }), false);
equal(haraIdentityCustomerMcpEnabled({ ...dev, ENVIRONMENT: "PROD" }), false);
equal(haraIdentityCustomerMcpEnabled(prod), true);
equal(haraIdentityCustomerMcpEnabled({ ...prod, CUSTOMER_MCP_EDGE_ENABLED: "false", CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "true" }), false);
equal(haraIdentityCustomerMcpAllowedHosts(dev), [host]);
equal(haraIdentityCustomerMcpAllowedHosts(prod), ["commander.haralabs.com.br"]);
const metadata = haraIdentityCustomerMcpProtectedResourceMetadata(
  new Request("https://" + host + "/.well-known/oauth-protected-resource/api/mcp"),
  { ...dev, CUSTOMER_MCP_RESOURCE: "https://commander.haralabs.com.br/api/mcp" },
);
equal(metadata.resource, "https://" + host + "/api/mcp");

const oldFetch = globalThis.fetch;
globalThis.fetch = async () => { throw new Error("UNEXPECTED_AUTH_NETWORK_REQUEST"); };
try {
  for (const [env, requestHost, expected] of [
    [dev, host, 401],
    [{ ...dev, CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: undefined }, host, 404],
    [prod, "commander.haralabs.com.br", 401],
    [{ ...prod, CUSTOMER_MCP_EDGE_ENABLED: "false" }, "commander.haralabs.com.br", 404],
    [{ ...prod, CUSTOMER_MCP_EDGE_ENABLED: "false", CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED: "true" }, "commander.haralabs.com.br", 404],
  ]) {
    const request = new Request("https://" + requestHost + "/api/mcp?profile=simple", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
    });
    const response = await worker.fetch(request, env);
    equal(response.status, expected);
    const body = await response.json();
    if (expected === 401) {
      equal(body.error, "invalid_token");
      assert.match(response.headers.get("www-authenticate"), new RegExp(requestHost.replaceAll(".", "\\.")));
      checks += 1;
    } else equal(body.code, "NOT_FOUND");
  }
  const response = await worker.fetch(new Request("https://" + host + "/.well-known/oauth-protected-resource/api/mcp"), dev);
  equal(response.status, 200);
  equal((await response.json()).resource, "https://" + host + "/api/mcp");
} finally {
  globalThis.fetch = oldFetch;
}
console.log("COMMANDER_CUSTOMER_MCP_DEV_OPTIN=PASS");
console.log("COMMANDER_CUSTOMER_MCP_DEV_WITHOUT_OPTIN=404");
console.log("COMMANDER_CUSTOMER_MCP_DEV_MISSING_REAL_BEARER=401");
console.log("COMMANDER_CUSTOMER_MCP_PROD_GUARD_UNCHANGED=PASS");
console.log("COMMANDER_CUSTOMER_MCP_DEV_RESOURCE_AND_HOST=PASS");
console.log("COMMANDER_CUSTOMER_MCP_DEV_OPTIN_CHECKS=" + checks);
