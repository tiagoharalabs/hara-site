import assert from "node:assert/strict";
import { verifyIdToken } from "../src/oidc.js";

const issuer = "https://auth.example.test/";
const clientId = "commander-client";
const nonce = "nonce-123";
const metadata = { jwks_uri: "https://auth.example.test/oauth/v2/keys" };

const { publicKey, privateKey } = await crypto.subtle.generateKey(
  { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
  true,
  ["sign", "verify"],
);
const publicJwk = await crypto.subtle.exportKey("jwk", publicKey);
publicJwk.kid = "test-key";
publicJwk.alg = "RS256";
publicJwk.use = "sig";

const originalFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  assert.equal(String(url), metadata.jwks_uri);
  assert.equal(init.redirect, "error");
  return Response.json({ keys: [publicJwk] });
};

function encodedJson(value) {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

async function signJwt(claims) {
  const header = encodedJson({ alg: "RS256", kid: "test-key", typ: "JWT" });
  const payload = encodedJson(claims);
  const signingInput = `${header}.${payload}`;
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    privateKey,
    new TextEncoder().encode(signingInput),
  );
  return `${signingInput}.${Buffer.from(signature).toString("base64url")}`;
}

const now = Math.floor(Date.now() / 1000);
const baseClaims = {
  iss: issuer,
  sub: "subject-1",
  aud: [clientId, "other-client"],
  nonce,
  exp: now + 300,
  iat: now,
};

const valid = await signJwt({ ...baseClaims, azp: clientId });
assert.equal(
  (await verifyIdToken({ idToken: valid, metadata, issuer, clientId, nonce })).sub,
  "subject-1",
);

const missingAzp = await signJwt(baseClaims);
await assert.rejects(
  verifyIdToken({ idToken: missingAzp, metadata, issuer, clientId, nonce }),
  /OIDC_AUTHORIZED_PARTY_MISSING/,
);

const wrongAzp = await signJwt({ ...baseClaims, azp: "other-client" });
await assert.rejects(
  verifyIdToken({ idToken: wrongAzp, metadata, issuer, clientId, nonce }),
  /OIDC_AUTHORIZED_PARTY_MISMATCH/,
);

const singleAudienceWrongAzp = await signJwt({ ...baseClaims, aud: clientId, azp: "other-client" });
await assert.rejects(
  verifyIdToken({ idToken: singleAudienceWrongAzp, metadata, issuer, clientId, nonce }),
  /OIDC_AUTHORIZED_PARTY_MISMATCH/,
);

for (const invalidAzp of [0, "", false, { client: clientId }]) {
  const token = await signJwt({ ...baseClaims, aud: clientId, azp: invalidAzp });
  await assert.rejects(
    verifyIdToken({ idToken: token, metadata, issuer, clientId, nonce }),
    /OIDC_AUTHORIZED_PARTY_INVALID/,
  );
}

const validNbf = await signJwt({ ...baseClaims, azp: clientId, nbf: now - 5 });
assert.equal(
  (await verifyIdToken({ idToken: validNbf, metadata, issuer, clientId, nonce })).sub,
  "subject-1",
);

const futureNbf = await signJwt({ ...baseClaims, azp: clientId, nbf: now + 120 });
await assert.rejects(
  verifyIdToken({ idToken: futureNbf, metadata, issuer, clientId, nonce }),
  /OIDC_ID_TOKEN_NOT_YET_VALID/,
);

const invalidNbf = await signJwt({ ...baseClaims, azp: clientId, nbf: "tomorrow" });
await assert.rejects(
  verifyIdToken({ idToken: invalidNbf, metadata, issuer, clientId, nonce }),
  /OIDC_ID_TOKEN_NBF_INVALID/,
);

const missingIat = await signJwt({ ...baseClaims, azp: clientId, iat: undefined });
await assert.rejects(
  verifyIdToken({ idToken: missingIat, metadata, issuer, clientId, nonce }),
  /OIDC_ID_TOKEN_IAT_INVALID/,
);

const stringIat = await signJwt({ ...baseClaims, azp: clientId, iat: "now" });
await assert.rejects(
  verifyIdToken({ idToken: stringIat, metadata, issuer, clientId, nonce }),
  /OIDC_ID_TOKEN_IAT_INVALID/,
);

const malformedAudience = await signJwt({
  ...baseClaims,
  aud: [clientId, 42],
  azp: clientId,
});
await assert.rejects(
  verifyIdToken({ idToken: malformedAudience, metadata, issuer, clientId, nonce }),
  /OIDC_AUDIENCE_MISMATCH/,
);

const unicodeSubject = await signJwt({
  ...baseClaims,
  sub: "subject-ç",
  azp: clientId,
});
await assert.rejects(
  verifyIdToken({ idToken: unicodeSubject, metadata, issuer, clientId, nonce }),
  /OIDC_SUBJECT_INVALID/,
);

for (const badIssuer of [
  "https://auth.example.test/?unexpected=1",
  "https://auth.example.test/#fragment",
  "https://user:pass@auth.example.test/",
]) {
  const token = await signJwt({ ...baseClaims, iss: badIssuer, azp: clientId });
  await assert.rejects(
    verifyIdToken({ idToken: token, metadata, issuer, clientId, nonce }),
    /OIDC_ISSUER_INVALID/,
  );
}

globalThis.fetch = originalFetch;

console.log("COMMANDER_OIDC_AZP_VALID=PASS");
console.log("COMMANDER_OIDC_MULTI_AUD_MISSING_AZP=DENIED");
console.log("COMMANDER_OIDC_WRONG_AZP=DENIED");
console.log("COMMANDER_OIDC_AZP_SHAPE=ENFORCED");
console.log("COMMANDER_OIDC_FUTURE_NBF=DENIED");
console.log("COMMANDER_OIDC_INVALID_NBF=DENIED");
console.log("COMMANDER_OIDC_REQUIRED_IAT=ENFORCED");
console.log("COMMANDER_OIDC_AUDIENCE_SHAPE=ENFORCED");
console.log("COMMANDER_OIDC_SUBJECT_SHAPE=ENFORCED");
console.log("COMMANDER_OIDC_ISSUER_COMPONENTS=ENFORCED");
