import assert from "node:assert/strict";
import { oidcDiscovery } from "../src/oidc.js";

const issuer = "https://auth.example.test/";
const discoveryUrl = "https://auth.example.test/.well-known/openid-configuration";
const base = {
  issuer: "https://auth.example.test",
  authorization_endpoint: "https://auth.example.test/oauth/v2/authorize?tenant=hara",
  token_endpoint: "https://auth.example.test/oauth/v2/token",
  jwks_uri: "https://auth.example.test/oauth/v2/keys",
  userinfo_endpoint: "https://auth.example.test/oidc/v1/userinfo",
};

async function discover(metadata) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    assert.equal(String(url), discoveryUrl);
    return Response.json(metadata);
  };
  try {
    return await oidcDiscovery(issuer);
  } finally {
    globalThis.fetch = originalFetch;
  }
}

const valid = await discover(base);
assert.equal(valid.authorization_endpoint, base.authorization_endpoint);

for (const field of ["authorization_endpoint", "token_endpoint", "jwks_uri", "userinfo_endpoint"]) {
  for (const invalid of [
    "http://auth.example.test/path",
    "https://user:pass@auth.example.test/path",
    "https://auth.example.test/path#fragment",
    "not-a-url",
  ]) {
    await assert.rejects(
      discover({ ...base, [field]: invalid }),
      /OIDC_DISCOVERY_ENDPOINT_INVALID/,
      field + ":" + invalid,
    );
  }
}

console.log("COMMANDER_OIDC_DISCOVERY_HTTPS=ENFORCED");
console.log("COMMANDER_OIDC_DISCOVERY_USERINFO_HTTPS=ENFORCED");
console.log("COMMANDER_OIDC_DISCOVERY_QUERY_ENDPOINT=ALLOWED");
