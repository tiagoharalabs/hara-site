import {
  introspectAccessToken,
  normalizeIssuer,
  oidcDiscovery,
  oidcUserInfo,
  sha256,
  verifyAccessToken,
} from "./oidc.js";

const PROD_MCP_PATH = "/api/mcp";
const PROD_MCP_METADATA_PATH = "/.well-known/oauth-protected-resource/api/mcp";
const opaqueInFlight = new Map();
const PROVIDER_FAILURE_CODES = new Set([
  "OIDC_PROVIDER_TIMEOUT", "OIDC_PROVIDER_UNAVAILABLE", "OIDC_PROVIDER_INVALID_RESPONSE",
  "OIDC_DISCOVERY_FAILED", "OIDC_DISCOVERY_INCOMPLETE", "OIDC_DISCOVERY_ENDPOINT_INVALID",
  "OIDC_DISCOVERY_ISSUER_MISMATCH", "OIDC_JWKS_FAILED", "OIDC_USERINFO_FAILED",
  "OIDC_INTROSPECTION_FAILED", "OIDC_USERINFO_UNAVAILABLE", "OIDC_INTROSPECTION_NOT_CONFIGURED",
  "OIDC_INTROSPECTION_ENDPOINT_INVALID", "OIDC_USERINFO_REDIRECT_DENIED",
  "OIDC_INTROSPECTION_REDIRECT_DENIED", "HARA_IDENTITY_MCP_ISSUER_CONFIG_INVALID",
  "HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISSING",
  "HARA_IDENTITY_MCP_PKCE_S256_REQUIRED", "HARA_IDENTITY_MCP_USERINFO_REQUIRED",
  "HARA_IDENTITY_MCP_INTROSPECTION_SECRET_MISSING", "HARA_IDENTITY_MCP_INTROSPECTION_ENDPOINT_MISSING",
]);

export function haraIdentityCustomerMcpProviderFailure(error) {
  return PROVIDER_FAILURE_CODES.has(String(error?.message || ""));
}

export function haraIdentityCustomerMcpUnavailable() {
  return Response.json({error:"temporarily_unavailable"},{status:503,
    headers:{"cache-control":"no-store","retry-after":"5","content-type":"application/json; charset=utf-8"}});
}

function decodeB64urlJson(value) {
  const text = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = text + "=".repeat((4 - (text.length % 4 || 4)) % 4);
  return JSON.parse(atob(padded));
}

function saneClientId(value) {
  const text = typeof value === "string" ? value : "";
  if (!text || text.length > 512 || /[\u0000-\u001f\u007f]/.test(text)) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_INVALID");
  }
  return text;
}

function jwtClientIdOrNull(accessToken) {
  const parts = String(accessToken || "").split(".");
  if (parts.length !== 3) return null;
  let header;
  let claims;
  try {
    header = decodeB64urlJson(parts[0]);
    claims = decodeB64urlJson(parts[1]);
  } catch (_error) {
    return null;
  }
  if (!header || typeof header !== "object" || !header.alg || !header.kid) return null;
  const clientId = typeof claims.client_id === "string" ? claims.client_id : "";
  const azp = typeof claims.azp === "string" ? claims.azp : "";
  if (!clientId && !azp) throw new Error("HARA_IDENTITY_MCP_CLIENT_BINDING_MISSING");
  if (clientId && azp && clientId !== azp) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_BINDING_CONFLICT");
  }
  return saneClientId(clientId || azp);
}

function stringList(value) {
  const values = Array.isArray(value) ? value : [value];
  return values.filter((item) => typeof item === "string" && item);
}

function scopeList(value) {
  return Array.isArray(value)
    ? value.map(String).filter(Boolean)
    : String(value || "").split(/\s+/).filter(Boolean);
}

function saneSubject(value) {
  const text = typeof value === "string" ? value : "";
  if (!text || text.length > 255 || !/^[ -~]+$/.test(text)) {
    throw new Error("HARA_IDENTITY_MCP_SUBJECT_INVALID");
  }
  return text;
}

export function validateOpaqueIntrospection({
  payload,
  issuer,
  projectAudience,
  introspectionClientId,
  userInfo,
  nowSeconds = Math.floor(Date.now() / 1000),
}) {
  if (!payload || payload.active !== true) {
    throw new Error("HARA_IDENTITY_MCP_INTROSPECTION_INACTIVE");
  }
  if (typeof payload.iss !== "string" || !payload.iss) {
    throw new Error("OIDC_PROVIDER_INVALID_RESPONSE");
  }
  if (normalizeIssuer(payload.iss) !== normalizeIssuer(issuer)) {
    throw new Error("HARA_IDENTITY_MCP_INTROSPECTION_ISSUER_MISMATCH");
  }

  const clientId = saneClientId(payload.client_id);
  const audiences = stringList(payload.aud);
  if (!audiences.includes(projectAudience)) {
    throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISMATCH");
  }
  if (!audiences.includes(introspectionClientId)) {
    throw new Error("HARA_IDENTITY_MCP_INTROSPECTION_AUD_MISMATCH");
  }
  if (!audiences.includes(clientId)) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_AUD_MISMATCH");
  }

  const scopes = scopeList(payload.scope);
  if (!scopes.includes("openid")) {
    throw new Error("HARA_IDENTITY_MCP_SCOPE_MISSING");
  }
  if (payload.exp !== undefined && (!Number.isFinite(payload.exp) || payload.exp < nowSeconds - 30)) {
    throw new Error("HARA_IDENTITY_MCP_TOKEN_EXPIRED");
  }
  if (payload.iat !== undefined && (!Number.isFinite(payload.iat) || payload.iat > nowSeconds + 60)) {
    throw new Error("HARA_IDENTITY_MCP_TOKEN_IAT_INVALID");
  }

  const userSubject = saneSubject(userInfo?.sub);
  if (payload.sub !== undefined && saneSubject(payload.sub) !== userSubject) {
    throw new Error("HARA_IDENTITY_MCP_SUBJECT_MISMATCH");
  }

  return {
    issuer: normalizeIssuer(payload.iss),
    subject: userSubject,
    client_id: clientId,
    client_binding: "introspection_client_id",
    audience_count: audiences.length,
    scopes,
    token_format: "OPAQUE",
  };
}

export function haraIdentityCustomerMcpEnabled(env) {
  return (
    String(env?.ENVIRONMENT || "") === "PROD"
    && String(env?.CUSTOMER_MCP_EDGE_ENABLED || "").trim().toLowerCase() === "true"
  );
}

export function haraIdentityCustomerMcpResource(request, env) {
  const configured = String(env?.CUSTOMER_MCP_RESOURCE || "").trim();
  return configured || new URL(PROD_MCP_PATH, new URL(request.url).origin).toString();
}

export function haraIdentityCustomerMcpMetadataUrl(request) {
  return new URL(PROD_MCP_METADATA_PATH, new URL(request.url).origin).toString();
}

export function haraIdentityCustomerMcpProtectedResourceMetadata(request, env) {
  if (!haraIdentityCustomerMcpEnabled(env)) {
    throw new Error("HARA_IDENTITY_CUSTOMER_MCP_DISABLED");
  }
  return {
    resource: haraIdentityCustomerMcpResource(request, env),
    authorization_servers: [normalizeIssuer(env.AUTH_ISSUER).replace(/\/$/, "")],
    bearer_methods_supported: ["header"],
    scopes_supported: ["openid", "email"],
  };
}

export function haraIdentityCustomerMcpUnauthorized(request) {
  const metadata = haraIdentityCustomerMcpMetadataUrl(request);
  return Response.json(
    { error: "invalid_token", error_description: "Missing or invalid access token" },
    {
      status: 401,
      headers: {
        "cache-control": "no-store",
        "content-type": "application/json; charset=utf-8",
        "www-authenticate":
          'Bearer realm="H.A.R.A. Commander", error="invalid_token", resource_metadata="' + metadata + '"',
      },
    },
  );
}

export async function verifyHaraIdentityCustomerMcpBearer(request, env) {
  if (!haraIdentityCustomerMcpEnabled(env)) {
    throw new Error("HARA_IDENTITY_CUSTOMER_MCP_DISABLED");
  }
  try { normalizeIssuer(env.AUTH_ISSUER); }
  catch (_error) { throw new Error("HARA_IDENTITY_MCP_ISSUER_CONFIG_INVALID"); }
  const projectAudience = String(env.HARA_IDENTITY_MCP_DCR_PROJECT_AUD || "").trim();
  if (!projectAudience) {
    throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISSING");
  }

  const authorization = String(request.headers.get("authorization") || "");
  const match = authorization.match(/^Bearer ([^\s]+)$/);
  if (!match) throw new Error("HARA_IDENTITY_MCP_BEARER_MISSING");

  const accessToken = match[1];
  const metadata = await oidcDiscovery(env.AUTH_ISSUER);
  if (!Array.isArray(metadata.code_challenge_methods_supported)
      || !metadata.code_challenge_methods_supported.includes("S256")) {
    throw new Error("HARA_IDENTITY_MCP_PKCE_S256_REQUIRED");
  }
  if (!metadata.userinfo_endpoint) {
    throw new Error("HARA_IDENTITY_MCP_USERINFO_REQUIRED");
  }

  const jwtClientId = jwtClientIdOrNull(accessToken);
  if (jwtClientId) {
    const result = await verifyAccessToken({
      accessToken,
      metadata,
      issuer: env.AUTH_ISSUER,
      clientId: jwtClientId,
      requiredScopes: ["openid"],
    });
    if (!result.audiences.includes(projectAudience)) {
      throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISMATCH");
    }
    return {
      issuer: normalizeIssuer(result.claims.iss),
      subject: saneSubject(result.claims.sub),
      client_id: jwtClientId,
      client_binding: result.client_binding,
      audience_count: result.audiences.length,
      scopes: result.scopes,
      token_format: "JWT",
    };
  }

  const introspectionClientId = saneClientId(
    String(env.HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_ID || "").trim(),
  );
  const introspectionClientSecret = String(
    env.HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_SECRET || "",
  );
  if (!introspectionClientSecret) {
    throw new Error("HARA_IDENTITY_MCP_INTROSPECTION_SECRET_MISSING");
  }
  if (!metadata.introspection_endpoint) {
    throw new Error("HARA_IDENTITY_MCP_INTROSPECTION_ENDPOINT_MISSING");
  }

  // Share only simultaneous checks for the same credential and provider
  // binding. A settled response is removed immediately: revocation has no
  // cache contract, so the next MCP call must ask the provider again.
  const key = await sha256(JSON.stringify([accessToken,normalizeIssuer(env.AUTH_ISSUER),
    projectAudience,introspectionClientId,introspectionClientSecret,
    metadata.introspection_endpoint,metadata.userinfo_endpoint]));
  const existing = opaqueInFlight.get(key);
  if (existing) return {...await existing,provider_fetches_started:0};
  const pending = Promise.all([
    introspectAccessToken({metadata,accessToken,clientId:introspectionClientId,
      clientSecret:introspectionClientSecret}),
    oidcUserInfo({metadata,accessToken}),
  ]).then(([payload,userInfo])=>validateOpaqueIntrospection({
    payload,issuer:env.AUTH_ISSUER,projectAudience,introspectionClientId,userInfo,
  }));
  opaqueInFlight.set(key,pending);
  try { return {...await pending,provider_fetches_started:2}; }
  finally { if (opaqueInFlight.get(key)===pending) opaqueInFlight.delete(key); }
}
