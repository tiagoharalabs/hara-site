import {
  normalizeIssuer,
  oidcDiscovery,
  verifyAccessToken,
} from "./oidc.js";

const DEV_MCP_PATH = "/api/dev/mcp";
const DEV_MCP_METADATA_PATH = "/.well-known/oauth-protected-resource/api/dev/mcp";

export function haraIdentityMcpDevEnabled(env) {
  return (
    String(env?.ENVIRONMENT || "") === "DEV"
    && String(env?.CUSTOMER_MCP_HARA_IDENTITY_AUTH || "").trim().toLowerCase() === "true"
  );
}

export function haraIdentityMcpDevResource(request) {
  return new URL(DEV_MCP_PATH, new URL(request.url).origin).toString();
}

export function haraIdentityMcpDevMetadataUrl(request) {
  return new URL(DEV_MCP_METADATA_PATH, new URL(request.url).origin).toString();
}

export function haraIdentityMcpDevProtectedResourceMetadata(request, env) {
  if (!haraIdentityMcpDevEnabled(env)) throw new Error("HARA_IDENTITY_MCP_DEV_DISABLED");
  return {
    resource: haraIdentityMcpDevResource(request),
    authorization_servers: [normalizeIssuer(env.AUTH_ISSUER).replace(/\/$/, "")],
    bearer_methods_supported: ["header"],
    scopes_supported: ["openid"],
  };
}

export function haraIdentityMcpDevUnauthorized(request) {
  const metadata = haraIdentityMcpDevMetadataUrl(request);
  return Response.json(
    { error: "invalid_token", error_description: "Missing or invalid access token" },
    {
      status: 401,
      headers: {
        "cache-control": "no-store",
        "content-type": "application/json; charset=utf-8",
        "www-authenticate": "Bearer realm=\"HARA Commander DEV\", error=\"invalid_token\", resource_metadata=\"" + metadata + "\"",
      },
    },
  );
}

export async function verifyHaraIdentityMcpDevBearer(request, env) {
  if (!haraIdentityMcpDevEnabled(env)) throw new Error("HARA_IDENTITY_MCP_DEV_DISABLED");
  const expectedClientId = String(env.HARA_IDENTITY_MCP_DCR_CLIENT_ID || "").trim();
  if (!expectedClientId) throw new Error("HARA_IDENTITY_MCP_DCR_CLIENT_ID_MISSING");

  const authorization = String(request.headers.get("authorization") || "");
  const match = authorization.match(/^Bearer ([^\s]+)$/);
  if (!match) throw new Error("HARA_IDENTITY_MCP_BEARER_MISSING");

  const metadata = await oidcDiscovery(env.AUTH_ISSUER);
  const result = await verifyAccessToken({
    accessToken: match[1],
    metadata,
    issuer: env.AUTH_ISSUER,
    clientId: expectedClientId,
    requiredScopes: ["openid"],
  });

  return {
    issuer: normalizeIssuer(result.claims.iss),
    subject: result.claims.sub,
    client_id: expectedClientId,
    client_binding: result.client_binding,
    audience_count: result.audiences.length,
    scopes: result.scopes,
  };
}
