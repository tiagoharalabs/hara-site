import assert from "node:assert/strict";
import { safeReturnTo } from "../src/auth.js";

const fallback = "/#dashboard";

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

console.log("COMMANDER_AUTH_RETURN_TO_SAME_ORIGIN=PASS");
console.log("COMMANDER_AUTH_RETURN_TO_BACKSLASH_OPEN_REDIRECT=BLOCKED");
