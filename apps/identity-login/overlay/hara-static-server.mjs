import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const root = "/app/public";
const port = 8080;
const allowedRoot = new Set([
  "/favicon.ico",
  "/hara-logo-light.svg",
  "/hara-logo-dark.svg",
  "/zitadel-logo-light.svg",
  "/zitadel-logo-dark.svg",
]);
const contentTypes = {
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webmanifest": "application/manifest+json",
  ".xml": "application/xml",
};

function resolvePath(url) {
  const pathname = new URL(url, "http://localhost").pathname;
  if (!allowedRoot.has(pathname) && !pathname.startsWith("/favicon/")) return null;
  const relative = normalize(pathname).replace(/^\/+/, "");
  if (relative.includes("..")) return null;
  return join(root, relative);
}

const server = createServer((req, res) => {
  const file = resolvePath(req.url || "/");
  if (!file) {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    return res.end("not found");
  }
  try {
    if (!statSync(file).isFile()) throw new Error("not file");
    res.writeHead(200, {
      "content-type": contentTypes[extname(file)] || "application/octet-stream",
      "cache-control": "public, max-age=300",
      "x-content-type-options": "nosniff",
    });
    createReadStream(file).pipe(res);
  } catch {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("not found");
  }
});

server.listen(port, "0.0.0.0");
