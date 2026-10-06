import { lookup } from "node:dns/promises";
import { request as httpsRequest } from "node:https";
import {
  CIMD_ADMISSION_LIMITS,
  isForbiddenCimdNetworkAddress,
  validateCimdClientIdUrl,
  validateCimdDocument,
} from "./cimd-policy.mjs";

const DEFAULT_TIMEOUT_MS=5000;

export async function resolveCimdPublicAddresses(hostname, resolver=lookup) {
  const rows=await resolver(hostname,{all:true,verbatim:true});
  if (!Array.isArray(rows) || rows.length === 0) throw new Error("CIMD_DNS_EMPTY");
  for (const row of rows) {
    if (!row || typeof row.address !== "string" || ![4,6].includes(Number(row.family))) {
      throw new Error("CIMD_DNS_RESULT_INVALID");
    }
    if (isForbiddenCimdNetworkAddress(row.address)) throw new Error("CIMD_DNS_PRIVATE_ADDRESS_FORBIDDEN");
  }
  return rows;
}

function readJsonResponse(response,{maxBytes}) {
  return new Promise((resolve,reject)=>{
    const status=Number(response.statusCode || 0);
    if (status !== 200) {
      response.resume();
      reject(new Error(status >= 300 && status < 400 ? "CIMD_REDIRECT_FORBIDDEN" : "CIMD_HTTP_STATUS_INVALID"));
      return;
    }
    const contentType=String(response.headers["content-type"] || "").toLowerCase();
    if (!contentType.includes("application/json")) {
      response.resume();
      reject(new Error("CIMD_CONTENT_TYPE_JSON_REQUIRED"));
      return;
    }
    const contentLength=Number(response.headers["content-length"] || 0);
    if (Number.isFinite(contentLength) && contentLength > maxBytes) {
      response.resume();
      reject(new Error("CIMD_DOCUMENT_TOO_LARGE"));
      return;
    }
    const chunks=[];
    let size=0;
    response.on("data",(chunk)=>{
      size += chunk.length;
      if (size > maxBytes) {
        response.destroy(new Error("CIMD_DOCUMENT_TOO_LARGE"));
        return;
      }
      chunks.push(chunk);
    });
    response.on("error",reject);
    response.on("end",()=>{
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(new Error("CIMD_JSON_INVALID"));
      }
    });
  });
}

export async function fetchAndValidateCimd(clientId,{
  resolver=lookup,
  timeoutMs=DEFAULT_TIMEOUT_MS,
  maxBytes=CIMD_ADMISSION_LIMITS.max_document_bytes,
}={}) {
  const normalized=validateCimdClientIdUrl(clientId);
  const url=new URL(normalized);
  const rows=await resolveCimdPublicAddresses(url.hostname,resolver);
  const selected=rows[0];

  const document=await new Promise((resolve,reject)=>{
    const req=httpsRequest({
      protocol:"https:",
      hostname:url.hostname,
      port:url.port || 443,
      path:url.pathname,
      method:"GET",
      servername:url.hostname,
      headers:{
        accept:"application/json",
        "user-agent":"HARA-Identity-CIMD/1",
        host:url.host,
      },
      lookup(_hostname,_options,callback) {
        callback(null,selected.address,selected.family);
      },
    },(response)=>{
      readJsonResponse(response,{maxBytes}).then(resolve,reject);
    });
    req.setTimeout(timeoutMs,()=>req.destroy(new Error("CIMD_FETCH_TIMEOUT")));
    req.on("error",reject);
    req.end();
  });

  return validateCimdDocument(document,normalized);
}
