import assert from "node:assert/strict";
import { authStatus, cookieValue, logout, resolvePortalSession, safeReturnTo } from "../src/auth.js";

const fallback = "/#dashboard";

const baseAuthEnv = {
  AUTH_ISSUER: "https://auth.example.test/",
  AUTH_CLIENT_ID: "client",
};
assert.equal(authStatus({ ...baseAuthEnv, AUTH_CLIENT_AUTH: "BASIC", AUTH_CLIENT_SECRET: "secret" }).configured, true);
assert.equal(authStatus({ ...baseAuthEnv, AUTH_CLIENT_AUTH: "BASIC" }).configured, false);
assert.equal(authStatus({ ...baseAuthEnv, AUTH_CLIENT_AUTH: "NONE" }).configured, true);
assert.equal(authStatus({ ...baseAuthEnv, AUTH_CLIENT_AUTH: "NONE", AUTH_CLIENT_SECRET: "stale-secret" }).configured, true);
assert.equal(authStatus({ ...baseAuthEnv, AUTH_CLIENT_AUTH: "INVALID", AUTH_CLIENT_SECRET: "secret" }).configured, false);
assert.equal(authStatus({ ...baseAuthEnv, AUTH_CLIENT_AUTH: "INVALID", AUTH_CLIENT_SECRET: "secret" }).client_auth, "INVALID");

assert.equal(safeReturnTo(), fallback);
assert.equal(safeReturnTo("/#devices"), "/#devices");
assert.equal(safeReturnTo("/path?x=1#section"), "/path?x=1#section");

for (const candidate of [
  "//evil.example/path",
  "/\\evil.example/path",
  "\\evil.example/path",
  "https://evil.example/path",
  "/\nLocation: https://evil.example/",
  "/" + "a".repeat(501),
]) {
  assert.equal(safeReturnTo(candidate), fallback, candidate);
}

const decodedBackslash = new URL(
  "https://commander.haralabs.com.br/auth/login?return_to=%2F%5Cevil.example%2Fpath"
).searchParams.get("return_to");
assert.equal(decodedBackslash, "/\\evil.example/path");
assert.equal(safeReturnTo(decodedBackslash), fallback);

assert.equal(
  new URL(safeReturnTo(decodedBackslash), "https://commander.haralabs.com.br").origin,
  "https://commander.haralabs.com.br"
);

console.log("COMMANDER_AUTH_CLIENT_AUTH_CONFIG=ENFORCED");
console.log("COMMANDER_AUTH_RETURN_TO_SAME_ORIGIN=PASS");
console.log("COMMANDER_AUTH_RETURN_TO_BACKSLASH_OPEN_REDIRECT=BLOCKED");

const malformedCookieRequest = new Request("https://commander.haralabs.com.br/api/portal/session", {
  headers: { cookie: "hara_commander_session=%E0%A4%A" },
});
assert.equal(cookieValue(malformedCookieRequest, "hara_commander_session"), null);
assert.equal(await resolvePortalSession(malformedCookieRequest, {}), null);

const malformedLogoutRequest = new Request("https://commander.haralabs.com.br/auth/logout", {
  method: "POST",
  headers: { cookie: "hara_commander_session=%E0%A4%A" },
});
const malformedLogoutResponse = await logout(malformedLogoutRequest, {});
assert.equal(malformedLogoutResponse.status, 204);
assert.equal(
  (malformedLogoutResponse.headers.get("set-cookie") || "").includes(
    "hara_commander_session=; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=0"
  ),
  true,
);

console.log("COMMANDER_AUTH_MALFORMED_COOKIE=IGNORED");
console.log("COMMANDER_AUTH_MALFORMED_COOKIE_LOGOUT=CLEARS_SESSION");
