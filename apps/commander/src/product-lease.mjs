const encoder = new TextEncoder();

export const PRODUCT_LEASE_ALG = "RS256";
export const PRODUCT_LEASE_KID = "commander-lease-v1";
export const PRODUCT_LEASE_AUDIENCE = "hara-commander-agent";

export const PRODUCT_LEASE_PUBLIC_JWK = Object.freeze({
  kty: "RSA",
  n: "pq_Ql3poia63FAgi3MwPXFe9M9LNyJXPMKsjII0d6zgeu0RUcWwFvdBOnjCt6b2bVfElQF4ykvKLxEF6anfQT00nOmI1crDUpLcmx34cB1yZPkDcXiNqkN1g0rkhlkWJXNkGye6jYM7WLxS_Y_jx0Taky-5pGFHmY70Mh1XNv9hGhfXeN6mV83n8-v1oFJ9S0mMjbACwzIGjPs70wb8mZdGRZU_oT0mGlAOvG2oIToEwWZCQbTVVgap0XF2mEeY8IkNWiDh2wYCiTeAWTH5M2tJnkBZC0lx1HLC6jwnRowjIDTJvQhLUzs58ilbDwWPSPihehJ9WiImvnYu0M6xy-Q",
  e: "AQAB",
  alg: PRODUCT_LEASE_ALG,
  use: "sig",
  kid: PRODUCT_LEASE_KID,
});

function b64url(bytes) {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  for (const value of view) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
}

function encodedJson(value) {
  return b64url(encoder.encode(JSON.stringify(value)));
}

function signingJwk(env) {
  let jwk;
  try {
    jwk = JSON.parse(String(env.PRODUCT_LEASE_PRIVATE_JWK || ""));
  } catch (_error) {
    throw new Error("PRODUCT_LEASE_SIGNING_KEY_INVALID");
  }
  if (
    !jwk
    || jwk.kty !== "RSA"
    || jwk.alg !== PRODUCT_LEASE_ALG
    || jwk.kid !== PRODUCT_LEASE_KID
    || !jwk.d
    || !jwk.n
    || !jwk.e
  ) {
    throw new Error("PRODUCT_LEASE_SIGNING_KEY_INVALID");
  }
  return jwk;
}

export async function signProductLease(env, lease, issuer) {
  if (!lease || lease.schema !== "hara.commander-device-product-lease.v1") {
    throw new Error("PRODUCT_LEASE_INVALID");
  }
  const issuedAt = Date.parse(String(lease.issued_at_utc || ""));
  const validUntil = Date.parse(String(lease.valid_until_utc || ""));
  if (!Number.isFinite(issuedAt) || !Number.isFinite(validUntil) || validUntil <= issuedAt) {
    throw new Error("PRODUCT_LEASE_INVALID");
  }
  const normalizedIssuer = new URL(String(issuer)).origin;
  const header = {
    alg: PRODUCT_LEASE_ALG,
    kid: PRODUCT_LEASE_KID,
    typ: "JWT",
  };
  const claims = {
    iss: normalizedIssuer,
    aud: PRODUCT_LEASE_AUDIENCE,
    sub: String(lease.device_id),
    jti: String(lease.lease_id),
    iat: Math.floor(issuedAt / 1000),
    exp: Math.floor(validUntil / 1000),
    lease,
  };
  const signingInput = encodedJson(header) + "." + encodedJson(claims);
  const key = await crypto.subtle.importKey(
    "jwk",
    signingJwk(env),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    encoder.encode(signingInput),
  );
  return signingInput + "." + b64url(signature);
}
