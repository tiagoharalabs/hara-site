import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { pathToFileURL } from "node:url";
const workerUrl = new URL("../src/worker.js", import.meta.url).href;
const baselineUrl = workerUrl + "?baseline";
const source = readFileSync(new URL(workerUrl), "utf8");
const replacement = `      const errorStatus = statusMap[code] || 500;
      const incidentId = errorStatus >= 500
        ? await emitDevSafeIncident(error, env, requestUrl.pathname)
        : null;
      const errorResponse = json(errorPayload, errorStatus);
      if (incidentId) errorResponse.headers.set("x-hara-dev-incident-id", incidentId);
      return errorResponse;`;
assert.equal(source.split(replacement).length, 2);
const base = source.replace('import { emitDevSafeIncident } from "./dev-safe-error-diagnostics.mjs";\n', "")
  .replace(replacement, "      return json(errorPayload, statusMap[code] || 500);");
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "cloudflare:workers") return {
      url: "data:text/javascript," + encodeURIComponent("export class DurableObject { constructor(ctx,env) { this.ctx=ctx; this.env=env; } }"), shortCircuit: true,
    };
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url === baselineUrl) return { format: "module", source: base, shortCircuit: true };
    return nextLoad(url, context);
  },
});
const { default: worker } = await import(workerUrl);
const { default: baselineWorker } = await import(baselineUrl);
const secret = "QA_RAW_MESSAGE_HEADER_COOKIE_NEVER_EXPORTED";
const token = "LOCAL_UNIT_TEST_TOKEN_NO_NETWORK";
const logs = [];
const oldError = console.error;
const oldFetch = globalThis.fetch;
console.error = value => logs.push(String(value));
globalThis.fetch = async () => { throw new Error("UNEXPECTED_NETWORK"); };
let checks = 0;
const eq = (a,b) => { assert.deepEqual(a,b); checks++; };
try {
  for (const [environment,flag,expectedLogs] of [["DEV","true",1],["DEV","false",0],["PROD","true",0]]) {
    const before = logs.length;
    const env = { ENVIRONMENT: environment, DEV_SAFE_ERROR_DIAGNOSTICS_ENABLED: flag,
      MCP_PRODUCT_TOKEN: token, DEVICE_EVENT_V2_ENABLED: "true", DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED: "true", DEVICE_CHANNEL: {},
      PRODUCT_DB: { prepare() { throw new TypeError("D1_ERROR: query timed out " + secret); } },
    };
    const request = new Request("https://unit.invalid/api/internal/device/transient-call", {
      method: "POST", headers: { "content-type": "application/json", "x-hara-mcp-product-token": token, cookie: secret },
      body: JSON.stringify({ issuer: "https://auth.haralabs.com.br/", subject: "unit-only-nonclient", request_id: "UNIT-HEALTH-001", tool_id: "hara.health", payload: {} }),
    });
    const baselineResponse = await baselineWorker.fetch(request.clone(),env);
    const baselineBody = await baselineResponse.json();
    const response = await worker.fetch(request,env);
    eq(response.status,baselineResponse.status);
    const responseBody = await response.json();
    eq(responseBody,baselineBody);
    if (environment === "DEV") { eq(response.status,500); eq(baselineBody,{ok:false,code:"INTERNAL_ERROR"}); }
    eq(logs.length-before,expectedLogs);
    const id = response.headers.get("x-hara-dev-incident-id");
    if (expectedLogs) {
      const incident = JSON.parse(logs.at(-1));
      eq(id,incident.incident_id);
      eq(incident.exception_class,"TypeError");
      eq(incident.safe_cause_class,"D1_TIMEOUT");
      eq(incident.route,"TRANSIENT_CALL");
      eq(JSON.stringify(incident).includes(secret),false);
      eq(JSON.stringify(incident).includes(token),false);
    } else eq(id,null);
  }
} finally {
  console.error = oldError;
  globalThis.fetch = oldFetch;
}
console.log(JSON.stringify({schema:"hara.dev-safe-error-worker-catch-tests.v1",state:"PASS",checks,scope:"actual Worker.fetch; prior catch loaded in memory for comparison; synthetic D1 fault only; no runtime mutation/network"}));
