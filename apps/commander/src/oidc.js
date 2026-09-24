const encoder = new TextEncoder();

function b64url(bytes) {
  let binary = "";
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (const byte of view) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeB64url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function randomToken(bytes = 32) {
  const buffer = new Uint8Array(bytes);
  crypto.getRandomValues(buffer);
  return b64url(buffer);
}

export async function sha256(value) {
  return b64url(await crypto.subtle.digest("SHA-256", encoder.encode(String(value))));
}

export function normalizeIssuer(value) {
  const issuer = String(value || "").trim();
  if (!issuer) throw new Error("OIDC_NOT_CONFIGURED");
  const url = new URL(issuer);
  if (
    url.protocol !== "https:"
    || url.username
    || url.password
    || url.search
    || url.hash
  ) {
    throw new Error("OIDC_ISSUER_INVALID");
  }
  if (!url.pathname.endsWith("/")) url.pathname += "/";
  return url.toString();
}

export async function oidcDiscovery(issuer) {
  const normalized = normalizeIssuer(issuer);
  const endpoint = new URL(".well-known/openid-configuration", normalized).toString();
  const response = await fetch(endpoint, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error("OIDC_DISCOVERY_FAILED");
  const metadata = await response.json();
  if (normalizeIssuer(metadata.issuer) !== normalized) throw new Error("OIDC_ISSUER_MISMATCH");
  for (const field of ["authorization_endpoint", "token_endpoint", "jwks_uri"]) {
    if (!metadata[field]) throw new Error("OIDC_DISCOVERY_INCOMPLETE");
  }
  return metadata;
}

export async function pkceChallenge(verifier) {
  return sha256(verifier);
}

export async function oidcUserInfo({ metadata, accessToken }) {
  if (!metadata?.userinfo_endpoint || !accessToken) throw new Error("OIDC_USERINFO_UNAVAILABLE");
  const response = await fetch(metadata.userinfo_endpoint, {
    headers: {
      accept: "application/json",
      authorization: "Bearer " + String(accessToken),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.sub) throw new Error("OIDC_USERINFO_FAILED");
  return payload;
}

function formUrlEncodeComponent(value) {
  return new URLSearchParams([["v", String(value)]]).toString().slice(2);
}

export async function exchangeAuthorizationCode({ metadata, clientId, clientSecret, code, verifier, redirectUri }) {
  const form = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    code_verifier: verifier,
    redirect_uri: redirectUri,
  });

  const headers = {
    "content-type": "application/x-www-form-urlencoded",
    accept: "application/json",
  };

  if (clientSecret) {
    const basic = btoa(
      formUrlEncodeComponent(clientId) + ":" + formUrlEncodeComponent(clientSecret),
    );
    headers.authorization = "Basic " + basic;
  } else {
    form.set("client_id", clientId);
  }

  const response = await fetch(metadata.token_endpoint, {
    method: "POST",
    headers,
    body: form.toString(),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.id_token) throw new Error("OIDC_TOKEN_EXCHANGE_FAILED");
  return payload;
}

export async function verifyIdToken({ idToken, metadata, issuer, clientId, nonce }) {
  const parts = String(idToken || "").split(".");
  if (parts.length !== 3) throw new Error("OIDC_ID_TOKEN_INVALID");

  const header = JSON.parse(new TextDecoder().decode(decodeB64url(parts[0])));
  const claims = JSON.parse(new TextDecoder().decode(decodeB64url(parts[1])));

  if (header.alg !== "RS256" || !header.kid) throw new Error("OIDC_ID_TOKEN_ALG_REJECTED");

  const jwksResponse = await fetch(metadata.jwks_uri, { headers: { accept: "application/json" } });
  if (!jwksResponse.ok) throw new Error("OIDC_JWKS_FAILED");
  const jwks = await jwksResponse.json();
  const jwk = (jwks.keys || []).find((item) => item.kid === header.kid && item.kty === "RSA");
  if (!jwk) throw new Error("OIDC_SIGNING_KEY_NOT_FOUND");

  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    decodeB64url(parts[2]),
    encoder.encode(parts[0] + "." + parts[1]),
  );
  if (!valid) throw new Error("OIDC_ID_TOKEN_SIGNATURE_INVALID");

  const expectedIssuer = normalizeIssuer(issuer);
  if (typeof claims.iss !== "string" || normalizeIssuer(claims.iss) !== expectedIssuer) {
    throw new Error("OIDC_ISSUER_MISMATCH");
  }
  const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (
    audiences.length === 0
    || audiences.some((audience) => typeof audience !== "string" || !audience)
    || !audiences.includes(clientId)
  ) {
    throw new Error("OIDC_AUDIENCE_MISMATCH");
  }
  if (
    claims.azp !== undefined
    && (typeof claims.azp !== "string" || !claims.azp)
  ) {
    throw new Error("OIDC_AUTHORIZED_PARTY_INVALID");
  }
  if (audiences.length > 1 && !claims.azp) throw new Error("OIDC_AUTHORIZED_PARTY_MISSING");
  if (claims.azp && claims.azp !== clientId) throw new Error("OIDC_AUTHORIZED_PARTY_MISMATCH");
  if (claims.nonce !== nonce) throw new Error("OIDC_NONCE_MISMATCH");
  if (!claims.sub || typeof claims.sub !== "string") throw new Error("OIDC_SUBJECT_MISSING");
  if (claims.sub.length > 255 || !/^[ -~]+$/.test(claims.sub)) {
    throw new Error("OIDC_SUBJECT_INVALID");
  }

  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(claims.exp) || claims.exp < now - 30) throw new Error("OIDC_ID_TOKEN_EXPIRED");
  if (claims.nbf !== undefined && !Number.isFinite(claims.nbf)) {
    throw new Error("OIDC_ID_TOKEN_NBF_INVALID");
  }
  if (Number.isFinite(claims.nbf) && claims.nbf > now + 30) {
    throw new Error("OIDC_ID_TOKEN_NOT_YET_VALID");
  }
  if (!Number.isFinite(claims.iat) || claims.iat > now + 60) {
    throw new Error("OIDC_ID_TOKEN_IAT_INVALID");
  }

  return claims;
}
