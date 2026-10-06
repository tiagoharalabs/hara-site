import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { pathToFileURL } from "node:url";
import { DCR_ADMISSION_LIMITS, validateDcrRegistration } from "./dcr-policy.mjs";

const REGISTRATION_ROOT="/oauth/v2/register";
const VALID_MODES=new Set(["closed","guarded"]);

function json(res,status,value,headers={}) {
  res.writeHead(status,{
    "content-type":"application/json; charset=utf-8",
    "cache-control":"no-store",
    "x-content-type-options":"nosniff",
    ...headers,
  });
  res.end(JSON.stringify(value));
}

function clientAddress(req) {
  const forwarded=String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  return forwarded || String(req.socket?.remoteAddress || "unknown");
}

function fixedWindowLimiter({limit,windowMs}) {
  const buckets=new Map();
  return (key)=>{
    const now=Date.now();
    const current=buckets.get(key);
    if (!current || now >= current.resetAt) {
      buckets.set(key,{count:1,resetAt:now+windowMs});
      return {ok:true,retryAfter:0};
    }
    current.count += 1;
    if (current.count <= limit) return {ok:true,retryAfter:0};
    return {ok:false,retryAfter:Math.max(1,Math.ceil((current.resetAt-now)/1000))};
  };
}

function readBody(req,maxBytes=DCR_ADMISSION_LIMITS.max_document_bytes) {
  return new Promise((resolve,reject)=>{
    const chunks=[];
    let size=0;
    req.on("data",(chunk)=>{
      size += chunk.length;
      if (size > maxBytes) {
        req.destroy(new Error("DCR_REQUEST_TOO_LARGE"));
        return;
      }
      chunks.push(chunk);
    });
    req.on("error",reject);
    req.on("end",()=>resolve(Buffer.concat(chunks)));
  });
}

function proxyToUpstream(req,res,{upstreamHost,upstreamPort,body,externalHost}) {
  return new Promise((resolve)=>{
    const headers={...req.headers};
    delete headers["content-length"];
    delete headers["connection"];
    delete headers["x-forwarded-for"];
    headers.host=externalHost;
    headers["x-forwarded-proto"]="https";
    if (body) headers["content-length"]=String(body.length);
    const upstream=httpRequest({
      hostname:upstreamHost,
      port:upstreamPort,
      method:req.method,
      path:new URL(req.url || "/", "http://localhost").pathname,
      headers,
    },(upstreamResponse)=>{
      const responseHeaders={};
      for (const [name,value] of Object.entries(upstreamResponse.headers)) {
        if (value !== undefined && !["connection","transfer-encoding"].includes(name.toLowerCase())) {
          responseHeaders[name]=value;
        }
      }
      res.writeHead(Number(upstreamResponse.statusCode || 502),responseHeaders);
      upstreamResponse.pipe(res);
      upstreamResponse.on("end",resolve);
    });
    upstream.on("error",()=>{
      if (!res.headersSent) json(res,502,{error:"temporarily_unavailable"});
      else res.end();
      resolve();
    });
    if (body) upstream.end(body);
    else req.pipe(upstream);
  });
}

export function createDcrGatewayServer({
  mode="closed",
  upstreamHost="zitadel-api",
  upstreamPort=8080,
  externalHost="auth.haralabs.com.br",
  allowCustomSchemes=true,
  registrationLimit=20,
  registrationWindowMs=60*60*1000,
}={}) {
  if (!VALID_MODES.has(mode)) throw new Error("DCR_GATEWAY_MODE_INVALID");
  const consumeRegistration=fixedWindowLimiter({limit:registrationLimit,windowMs:registrationWindowMs});

  return createServer(async(req,res)=>{
    const pathname=new URL(req.url || "/", "http://localhost").pathname;
    const method=String(req.method || "GET").toUpperCase();

    if (pathname === "/healthz") {
      return json(res,200,{ok:true,component:"hara-identity-dcr-gateway",mode});
    }
    if (!(pathname === REGISTRATION_ROOT || pathname.startsWith(REGISTRATION_ROOT+"/"))) {
      return json(res,404,{error:"not_found"});
    }
    if (mode !== "guarded") {
      return json(res,404,{error:"not_found"});
    }

    if (!["POST","GET","PUT","DELETE"].includes(method)) {
      res.setHeader("allow","POST, GET, PUT, DELETE");
      return json(res,405,{error:"method_not_allowed"});
    }

    let body=null;
    if (method === "POST" || method === "PUT") {
      const contentType=String(req.headers["content-type"] || "").toLowerCase();
      if (!contentType.includes("application/json")) {
        return json(res,415,{error:"invalid_client_metadata"});
      }
      try {
        body=await readBody(req);
      } catch {
        return json(res,413,{error:"invalid_client_metadata"});
      }
      let input;
      try { input=JSON.parse(body.toString("utf8")); }
      catch { return json(res,400,{error:"invalid_client_metadata"}); }

      if (method === "POST" && pathname === REGISTRATION_ROOT) {
        const rate=consumeRegistration(clientAddress(req));
        if (!rate.ok) {
          return json(res,429,{error:"temporarily_unavailable"},{"retry-after":String(rate.retryAfter)});
        }
      }

      try {
        if (method === "POST") {
          body=Buffer.from(JSON.stringify(validateDcrRegistration(input,{allowCustomSchemes})));
        } else {
          const registeredClientId=String(input.client_id || "");
          const validated=validateDcrRegistration(input,{allowCustomSchemes});
          body=Buffer.from(JSON.stringify({client_id:registeredClientId,...validated}));
        }
      } catch(error) {
        return json(res,400,{
          error:"invalid_client_metadata",
          error_description:String(error?.message || "DCR_INVALID").slice(0,120),
        });
      }
    } else {
      const authorization=String(req.headers.authorization || "");
      if (!authorization.startsWith("Bearer ")) {
        return json(res,401,{error:"invalid_token"},{"www-authenticate":'Bearer error="invalid_token"'});
      }
    }

    return proxyToUpstream(req,res,{upstreamHost,upstreamPort,body,externalHost});
  });
}

function isDirectExecution() {
  const entry=process.argv[1];
  return Boolean(entry) && import.meta.url === pathToFileURL(entry).href;
}

if (isDirectExecution()) {
  const mode=String(process.env.HARA_DCR_GATEWAY_MODE || "closed").toLowerCase();
  const port=Number(process.env.PORT || 8082);
  createDcrGatewayServer({
    mode,
    upstreamHost:process.env.HARA_DCR_UPSTREAM_HOST || "zitadel-api",
    upstreamPort:Number(process.env.HARA_DCR_UPSTREAM_PORT || 8080),
    externalHost:process.env.HARA_IDENTITY_HOST || "auth.haralabs.com.br",
    allowCustomSchemes:String(process.env.HARA_DCR_ALLOW_CUSTOM_SCHEMES || "true").toLowerCase() === "true",
  }).listen(port,"0.0.0.0");
}
