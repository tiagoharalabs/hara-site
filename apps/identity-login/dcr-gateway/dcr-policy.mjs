const MAX_DCR_BYTES=64*1024;
const MAX_REDIRECT_URIS=16;
const MAX_URI_LENGTH=2048;
const CUSTOM_SCHEME=/^[a-z][a-z0-9+.-]*:$/i;
const DENIED_SCHEMES=new Set(["data:","file:","javascript:","vbscript:","blob:"]);

function exactStrings(value,code,{min=1,max=32}={}) {
  if (!Array.isArray(value) || value.length < min || value.length > max) throw new Error(code);
  const result=value.map((item)=>String(item || ""));
  if (result.some((item)=>!item)) throw new Error(code);
  return result;
}

function loopbackHost(hostname) {
  const h=String(hostname || "").toLowerCase().replace(/^\[/,"").replace(/\]$/,"");
  return h === "localhost" || h === "127.0.0.1" || h === "::1";
}

export function classifyDcrRedirectUri(value) {
  const raw=String(value || "");
  if (!raw || raw.length > MAX_URI_LENGTH) throw new Error("DCR_REDIRECT_URI_INVALID");
  let url;
  try { url=new URL(raw); }
  catch { throw new Error("DCR_REDIRECT_URI_INVALID"); }
  if (url.username || url.password || url.hash) throw new Error("DCR_REDIRECT_URI_COMPONENT_FORBIDDEN");

  if (url.protocol === "https:") return { uri:url.toString(), type:"web" };
  if (url.protocol === "http:" && loopbackHost(url.hostname)) {
    return { uri:url.toString(), type:"loopback" };
  }
  if (
    CUSTOM_SCHEME.test(url.protocol)
    && !DENIED_SCHEMES.has(url.protocol.toLowerCase())
    && !["http:","https:"].includes(url.protocol.toLowerCase())
  ) {
    return { uri:url.toString(), type:"custom" };
  }
  throw new Error("DCR_REDIRECT_URI_SCHEME_FORBIDDEN");
}

export function validateDcrRegistration(document,{allowCustomSchemes=true}={}) {
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("DCR_DOCUMENT_OBJECT_REQUIRED");
  }
  const redirectUris=exactStrings(
    document.redirect_uris,
    "DCR_REDIRECT_URIS_INVALID",
    {min:1,max:MAX_REDIRECT_URIS},
  ).map(classifyDcrRedirectUri);
  if (new Set(redirectUris.map((item)=>item.uri)).size !== redirectUris.length) {
    throw new Error("DCR_REDIRECT_URI_DUPLICATE");
  }
  if (!allowCustomSchemes && redirectUris.some((item)=>item.type === "custom")) {
    throw new Error("DCR_CUSTOM_SCHEME_DISABLED");
  }

  const responseTypes=document.response_types === undefined
    ? ["code"]
    : exactStrings(document.response_types,"DCR_RESPONSE_TYPES_INVALID",{min:1,max:4});
  if (responseTypes.some((item)=>item !== "code")) throw new Error("DCR_RESPONSE_TYPE_NOT_ALLOWED");

  const grantTypes=document.grant_types === undefined
    ? ["authorization_code","refresh_token"]
    : exactStrings(document.grant_types,"DCR_GRANT_TYPES_INVALID",{min:1,max:4});
  const allowedGrants=new Set(["authorization_code","refresh_token"]);
  if (!grantTypes.includes("authorization_code")) throw new Error("DCR_AUTHORIZATION_CODE_REQUIRED");
  if (grantTypes.some((item)=>!allowedGrants.has(item))) throw new Error("DCR_GRANT_TYPE_NOT_ALLOWED");

  const tokenAuth=String(document.token_endpoint_auth_method || "none");
  if (tokenAuth !== "none") throw new Error("DCR_PUBLIC_CLIENT_REQUIRED");

  const clientName=String(document.client_name || "MCP Client").trim();
  if (!clientName || clientName.length > 160) throw new Error("DCR_CLIENT_NAME_INVALID");

  const requestedType=String(document.application_type || "").trim();
  if (requestedType && !["web","native"].includes(requestedType)) {
    throw new Error("DCR_APPLICATION_TYPE_INVALID");
  }
  const needsNative=redirectUris.some((item)=>item.type === "custom" || item.type === "loopback");
  const applicationType=requestedType || (needsNative ? "native" : "web");
  if (needsNative && applicationType !== "native") throw new Error("DCR_NATIVE_REDIRECT_REQUIRES_NATIVE_APP");

  return Object.freeze({
    client_name:clientName,
    application_type:applicationType,
    redirect_uris:redirectUris.map((item)=>item.uri),
    response_types:responseTypes,
    grant_types:grantTypes,
    token_endpoint_auth_method:"none",
  });
}

export const DCR_ADMISSION_LIMITS=Object.freeze({
  max_document_bytes:MAX_DCR_BYTES,
  max_redirect_uris:MAX_REDIRECT_URIS,
  max_uri_length:MAX_URI_LENGTH,
});
