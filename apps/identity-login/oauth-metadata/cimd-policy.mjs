import { isIP } from "node:net";

const MAX_CIMD_BYTES = 64 * 1024;
const MAX_REDIRECT_URIS = 16;

function normalizedHostname(hostname) {
  return String(hostname || "")
    .toLowerCase()
    .replace(/^\[/, "")
    .replace(/\]$/, "")
    .replace(/\.$/, "");
}

function ipv4Parts(hostname) {
  if (isIP(hostname) !== 4) return null;
  return hostname.split(".").map(Number);
}

function isBlockedIpv4(hostname) {
  const p=ipv4Parts(hostname);
  if (!p) return false;
  const [a,b,c]=p;
  return (
    a === 0
    || a === 10
    || a === 127
    || (a === 100 && b >= 64 && b <= 127)
    || (a === 169 && b === 254)
    || (a === 172 && b >= 16 && b <= 31)
    || (a === 192 && b === 0 && c === 0)
    || (a === 192 && b === 0 && c === 2)
    || (a === 192 && b === 168)
    || (a === 198 && (b === 18 || b === 19))
    || (a === 198 && b === 51 && c === 100)
    || (a === 203 && b === 0 && c === 113)
    || a >= 224
  );
}

function isBlockedIpv6(hostname) {
  if (isIP(hostname) !== 6) return false;
  const h=hostname.toLowerCase();
  return (
    h === "::"
    || h === "::1"
    || h.startsWith("fc")
    || h.startsWith("fd")
    || h.startsWith("fe8")
    || h.startsWith("fe9")
    || h.startsWith("fea")
    || h.startsWith("feb")
    || h.startsWith("ff")
    || h.startsWith("2001:db8:")
  );
}

export function isForbiddenCimdNetworkAddress(address) {
  const host=normalizedHostname(address);
  return isBlockedIpv4(host) || isBlockedIpv6(host);
}

export function validateCimdClientIdUrl(value) {
  let url;
  try { url=new URL(String(value || "")); }
  catch { throw new Error("CIMD_CLIENT_ID_URL_INVALID"); }

  if (url.protocol !== "https:") throw new Error("CIMD_CLIENT_ID_HTTPS_REQUIRED");
  if (url.username || url.password) throw new Error("CIMD_CLIENT_ID_USERINFO_FORBIDDEN");
  if (url.hash) throw new Error("CIMD_CLIENT_ID_FRAGMENT_FORBIDDEN");
  if (url.search) throw new Error("CIMD_CLIENT_ID_QUERY_FORBIDDEN");
  if (!url.pathname || url.pathname === "/") throw new Error("CIMD_CLIENT_ID_NONROOT_PATH_REQUIRED");
  if (url.pathname.split("/").some((part)=>part === "." || part === "..")) {
    throw new Error("CIMD_CLIENT_ID_DOT_SEGMENT_FORBIDDEN");
  }

  const hostname=normalizedHostname(url.hostname);
  if (
    !hostname
    || hostname === "localhost"
    || hostname.endsWith(".localhost")
    || hostname.endsWith(".local")
    || isBlockedIpv4(hostname)
    || isBlockedIpv6(hostname)
  ) {
    throw new Error("CIMD_CLIENT_ID_HOST_FORBIDDEN");
  }

  return url.toString();
}

function validateRedirectUri(value) {
  let url;
  try { url=new URL(String(value || "")); }
  catch { throw new Error("CIMD_REDIRECT_URI_INVALID"); }

  if (url.username || url.password || url.hash) throw new Error("CIMD_REDIRECT_URI_COMPONENT_FORBIDDEN");
  if (url.protocol === "https:") return url.toString();

  const host=normalizedHostname(url.hostname);
  const loopback=(host === "127.0.0.1" || host === "::1");
  if (url.protocol === "http:" && loopback) return url.toString();

  throw new Error("CIMD_REDIRECT_URI_HTTPS_OR_LOOPBACK_REQUIRED");
}

function exactStringArray(value, code, { min=1, max=32 }={}) {
  if (!Array.isArray(value) || value.length < min || value.length > max) throw new Error(code);
  const out=value.map((item)=>String(item || ""));
  if (out.some((item)=>!item)) throw new Error(code);
  return out;
}

export function validateCimdDocument(document, expectedClientId) {
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("CIMD_DOCUMENT_OBJECT_REQUIRED");
  }

  const clientId=validateCimdClientIdUrl(document.client_id);
  const expected=validateCimdClientIdUrl(expectedClientId);
  if (clientId !== expected) throw new Error("CIMD_CLIENT_ID_MISMATCH");

  const clientName=String(document.client_name || "").trim();
  if (!clientName || clientName.length > 160) throw new Error("CIMD_CLIENT_NAME_INVALID");

  const redirectUris=exactStringArray(
    document.redirect_uris,
    "CIMD_REDIRECT_URIS_INVALID",
    { min:1, max:MAX_REDIRECT_URIS },
  ).map(validateRedirectUri);

  const responseTypes=document.response_types === undefined
    ? ["code"]
    : exactStringArray(document.response_types,"CIMD_RESPONSE_TYPES_INVALID",{min:1,max:4});
  if (responseTypes.some((value)=>value !== "code")) throw new Error("CIMD_RESPONSE_TYPE_NOT_ALLOWED");

  const grantTypes=document.grant_types === undefined
    ? ["authorization_code"]
    : exactStringArray(document.grant_types,"CIMD_GRANT_TYPES_INVALID",{min:1,max:4});
  const allowedGrants=new Set(["authorization_code","refresh_token"]);
  if (grantTypes.some((value)=>!allowedGrants.has(value))) throw new Error("CIMD_GRANT_TYPE_NOT_ALLOWED");
  if (!grantTypes.includes("authorization_code")) throw new Error("CIMD_AUTHORIZATION_CODE_REQUIRED");

  const tokenAuth=String(document.token_endpoint_auth_method || "none");
  if (tokenAuth !== "none") throw new Error("CIMD_PUBLIC_CLIENT_REQUIRED");

  return Object.freeze({
    client_id:clientId,
    client_name:clientName,
    redirect_uris:redirectUris,
    response_types:responseTypes,
    grant_types:grantTypes,
    token_endpoint_auth_method:"none",
  });
}

export const CIMD_ADMISSION_LIMITS = Object.freeze({
  max_document_bytes:MAX_CIMD_BYTES,
  max_redirect_uris:MAX_REDIRECT_URIS,
});
