import {
  normalizeIssuer,
  oidcDiscovery,
  verifyAccessToken,
} from "./oidc.js";

const PROD_MCP_PATH = "/api/mcp";
const PROD_MCP_METADATA_PATH = "/.well-known/oauth-protected-resource/api/mcp";

function decodeB64urlJson(value) {
  try {
    const text = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = text + "=".repeat((4 - (text.length % 4 || 4)) % 4);
    return JSON.parse(atob(padded));
  } catch (_error) {
    throw new Error("HARA_IDENTITY_MCP_TOKEN_INVALID");
  }
}

function tokenClientId(accessToken) {
  const parts = String(accessToken || "").split(".");
  if (parts.length !== 3) throw new Error("HARA_IDENTITY_MCP_TOKEN_NOT_JWT");
  const claims = decodeB64urlJson(parts[1]);
  const clientId = typeof claims.client_id === "string" ? claims.client_id : "";
  const azp = typeof claims.azp === "string" ? claims.azp : "";
  if (!clientId && !azp) throw new Error("HARA_IDENTITY_MCP_CLIENT_BINDING_MISSING");
  if (clientId && azp && clientId !== azp) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_BINDING_CONFLICT");
  }
  const selected = clientId || azp;
  if (!selected || selected.length > 512 || /[\u0000-\u001f\u007f]/.test(selected)) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_INVALID");
  }
  return selected;
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
  const projectAudience = String(env.HARA_IDENTITY_MCP_DCR_PROJECT_AUD || "").trim();
  if (!projectAudience) {
    throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISSING");
  }

  const authorization = String(request.headers.get("authorization") || "");
  const match = authorization.match(/^Bearer ([^\s]+)$/);
  if (!match) throw new Error("HARA_IDENTITY_MCP_BEARER_MISSING");

  const accessToken = match[1];
  const clientId = tokenClientId(accessToken);
  const metadata = await oidcDiscovery(env.AUTH_ISSUER);
  if (!Array.isArray(metadata.code_challenge_methods_supported)
      || !metadata.code_challenge_methods_supported.includes("S256")) {
    throw new Error("HARA_IDENTITY_MCP_PKCE_S256_REQUIRED");
  }
  if (!metadata.userinfo_endpoint) {
    throw new Error("HARA_IDENTITY_MCP_USERINFO_REQUIRED");
  }

  const result = await verifyAccessToken({
    accessToken,
    metadata,
    issuer: env.AUTH_ISSUER,
    clientId,
    requiredScopes: ["openid"],
  });
  if (!result.audiences.includes(projectAudience)) {
    throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISMATCH");
  }

  return {
    issuer: normalizeIssuer(result.claims.iss),
    subject: result.claims.sub,
    client_id: clientId,
    client_binding: result.client_binding,
    audience_count: result.audiences.length,
    scopes: result.scopes,
  };
}
