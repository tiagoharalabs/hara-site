import assert from "node:assert/strict";
import { exchangeAuthorizationCode, oidcUserInfo } from "../src/oidc.js";

const originalFetch = globalThis.fetch;
const calls = [];

globalThis.fetch = async (url, init = {}) => {
  calls.push({ url: String(url), init });
  if (String(url).endsWith("/token")) {
    return Response.json({ id_token: "header.payload.signature", access_token: "access" });
  }
  if (String(url).endsWith("/userinfo")) {
    return Response.json({ sub: "subject-1", email: "user@example.test" });
  }
  throw new Error("UNEXPECTED_FETCH");
};

try {
  const metadata = {
    token_endpoint: "https://auth.example.test/token",
    userinfo_endpoint: "https://auth.example.test/userinfo",
  };

  await exchangeAuthorizationCode({
    metadata,
    clientId: "client",
    clientSecret: "secret",
    clientAuth: "BASIC",
    code: "code",
    verifier: "verifier",
    redirectUri: "https://commander.example.test/auth/callback",
  });

  await oidcUserInfo({ metadata, accessToken: "access" });

  assert.equal(calls.length, 2);
  for (const call of calls) assert.equal(call.init.redirect, "error");
  assert.equal(calls[0].init.method, "POST");
  assert.match(String(calls[0].init.headers.authorization), /^Basic /);
  assert.equal(new URLSearchParams(calls[0].init.body).has("client_id"), false);
  assert.match(String(calls[1].init.headers.authorization), /^Bearer /);

  calls.length = 0;
  await exchangeAuthorizationCode({
    metadata,
    clientId: "public-client",
    clientSecret: "stale-secret-must-be-ignored",
    clientAuth: "NONE",
    code: "code",
    verifier: "verifier",
    redirectUri: "https://commander.example.test/auth/callback",
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.headers.authorization, undefined);
  assert.equal(new URLSearchParams(calls[0].init.body).get("client_id"), "public-client");

  await assert.rejects(
    exchangeAuthorizationCode({
      metadata,
      clientId: "client",
      clientSecret: "secret",
      clientAuth: "INVALID",
      code: "code",
      verifier: "verifier",
      redirectUri: "https://commander.example.test/auth/callback",
    }),
    /OIDC_CLIENT_AUTH_INVALID/,
  );
} finally {
  globalThis.fetch = originalFetch;
}

console.log("COMMANDER_OIDC_CLIENT_AUTH_METHOD=ENFORCED");
console.log("COMMANDER_OIDC_TOKEN_REDIRECT=FAIL_CLOSED");
console.log("COMMANDER_OIDC_USERINFO_REDIRECT=FAIL_CLOSED");
