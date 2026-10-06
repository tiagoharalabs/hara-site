import { createServer } from "node:http";
import { pathToFileURL } from "node:url";

export function oauthMetadataForIssuer(value) {
  const issuer=String(value || "https://auth.haralabs.com.br").replace(/\/$/, "");
  if (!issuer.startsWith("https://")) throw new Error("HARA_IDENTITY_ISSUER_HTTPS_REQUIRED");
  return Object.freeze({
    issuer,
    authorization_endpoint: issuer + "/oauth/v2/authorize",
    token_endpoint: issuer + "/oauth/v2/token",
    introspection_endpoint: issuer + "/oauth/v2/introspect",
    revocation_endpoint: issuer + "/oauth/v2/revoke",
    jwks_uri: issuer + "/oauth/v2/keys",
    scopes_supported: ["openid", "profile", "email", "offline_access"],
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none", "client_secret_basic", "client_secret_post"],
    client_id_metadata_document_supported: false,
  });
}

function json(res, status, value) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "public, max-age=300",
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
  });
  res.end(JSON.stringify(value));
}

export function createOAuthMetadataServer({ issuer }={}) {
  const metadata=oauthMetadataForIssuer(issuer);
  return createServer((req, res) => {
    const method=String(req.method || "GET").toUpperCase();
    const pathname=new URL(req.url || "/", "http://localhost").pathname;

    if (pathname === "/healthz") {
      if (!["GET","HEAD"].includes(method)) return json(res,405,{error:"method_not_allowed"});
      if (method === "HEAD") {
        res.writeHead(204,{"cache-control":"no-store"});
        return res.end();
      }
      return json(res,200,{ok:true,component:"hara-identity-oauth-metadata"});
    }

    if (pathname !== "/.well-known/oauth-authorization-server") {
      return json(res,404,{error:"not_found"});
    }
    if (!["GET","HEAD"].includes(method)) {
      return json(res,405,{error:"method_not_allowed"});
    }
    if (method === "HEAD") {
      res.writeHead(200,{
        "content-type":"application/json; charset=utf-8",
        "cache-control":"public, max-age=300",
        "x-content-type-options":"nosniff",
      });
      return res.end();
    }
    return json(res,200,metadata);
  });
}

function isDirectExecution() {
  const entry=process.argv[1];
  return Boolean(entry) && import.meta.url === pathToFileURL(entry).href;
}

if (isDirectExecution()) {
  const issuer=process.env.HARA_IDENTITY_ISSUER || "https://auth.haralabs.com.br";
  const port=Number(process.env.PORT || 8081);
  createOAuthMetadataServer({issuer}).listen(port,"0.0.0.0");
}
