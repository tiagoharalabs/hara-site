import {
  normalizeIssuer,
  oidcDiscovery,
  verifyAccessToken,
} from "./oidc.js";

const DEFAULT_RESOURCE_PATH = "/api/mcp";
const DEFAULT_METADATA_PATH = "/.well-known/oauth-protected-resource";

function b64urlDecodeText(value) {
  const text = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = text + "=".repeat((4 - (text.length % 4 || 4)) % 4);
  return atob(padded);
}

function unverifiedClientId(accessToken) {
  const parts = String(accessToken || "").split(".");
  if (parts.length !== 3) throw new Error("HARA_IDENTITY_MCP_TOKEN_NOT_JWT");
  let claims;
  try {
    claims = JSON.parse(b64urlDecodeText(parts[1]));
  } catch (_error) {
    throw new Error("HARA_IDENTITY_MCP_TOKEN_INVALID");
  }
  const clientId = typeof claims.client_id === "string" ? claims.client_id : "";
  const azp = typeof claims.azp === "string" ? claims.azp : "";
  if (!clientId && !azp) throw new Error("HARA_IDENTITY_MCP_CLIENT_BINDING_MISSING");
  if (clientId && azp && clientId !== azp) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_BINDING_CONFLICT");
  }
  const selected = clientId || azp;
  if (selected.length > 512 || /[\u0000-\u001f\u007f]/.test(selected)) {
    throw new Error("HARA_IDENTITY_MCP_CLIENT_INVALID");
  }
  return selected;
}

export function customerMcpEnabled(env) {
  return (
    ["DEV", "PROD"].includes(String(env?.ENVIRONMENT || ""))
    && String(env?.CUSTOMER_MCP_EDGE_ENABLED || "").trim().toLowerCase() === "true"
  );
}

export function customerMcpResource(request, env) {
  const configured = String(env?.CUSTOMER_MCP_RESOURCE || "").trim();
  if (configured) return configured;
  return new URL(DEFAULT_RESOURCE_PATH, new URL(request.url).origin).toString();
}

export function customerMcpMetadataUrl(request) {
  return new URL(DEFAULT_METADATA_PATH, new URL(request.url).origin).toString();
}

export function customerMcpProtectedResourceMetadata(request, env) {
  if (!customerMcpEnabled(env)) throw new Error("CUSTOMER_MCP_EDGE_DISABLED");
  return {
    resource: customerMcpResource(request, env),
    authorization_servers: [normalizeIssuer(env.AUTH_ISSUER).replace(/\/$/, "")],
    bearer_methods_supported: ["header"],
    scopes_supported: ["openid", "email"],
  };
}

export function customerMcpUnauthorized(request) {
  const metadata = customerMcpMetadataUrl(request);
  return Response.json(
    {
      error: "invalid_token",
      error_description: "Missing or invalid access token",
    },
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

export async function verifyCustomerMcpBearer(request, env) {
  if (!customerMcpEnabled(env)) throw new Error("CUSTOMER_MCP_EDGE_DISABLED");

  const authorization = String(request.headers.get("authorization") || "");
  const match = authorization.match(/^Bearer ([^\s]+)$/);
  if (!match) throw new Error("HARA_IDENTITY_MCP_BEARER_MISSING");

  const accessToken = match[1];
  const clientId = unverifiedClientId(accessToken);
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

  const requiredProjectAudience = String(env.HARA_IDENTITY_MCP_DCR_PROJECT_AUD || "").trim();
  if (env.ENVIRONMENT === "PROD" && !requiredProjectAudience) {
    throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISSING");
  }
  if (requiredProjectAudience && !result.audiences.includes(requiredProjectAudience)) {
    throw new Error("HARA_IDENTITY_MCP_DCR_PROJECT_AUD_MISMATCH");
  }

  return {
    issuer: normalizeIssuer(result.claims.iss),
    subject: result.claims.sub,
    client_id: clientId,
    client_binding: result.client_binding,
    audiences: result.audiences,
    scopes: result.scopes,
  };
}
