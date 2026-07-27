import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { handleRequest } from "../src/server/handler.js";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const build = spawnSync(process.execPath, ["scripts/build-static.js"], { cwd: root, stdio: "inherit" }); if (build.status !== 0) process.exit(build.status ?? 1);
const dist = path.join(root, "dist"), port = Number(process.env.PORT ?? 4173);
const server = http.createServer(async (req, res) => {
  try {
    const chunks = []; for await (const chunk of req) chunks.push(chunk); const body = Buffer.concat(chunks);
    const request = new Request(`http://localhost:${port}${req.url}`, { method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method ?? "GET") ? undefined : body });
    const response = await handleRequest(request, { ASSETS: { fetch: serveAsset } });
    res.writeHead(response.status, Object.fromEntries(response.headers)); res.end(Buffer.from(await response.arrayBuffer()));
  } catch (error) { res.writeHead(500, { "content-type": "text/plain" }); res.end("本地服务发生错误"); console.error(error); }
});
server.listen(port, () => console.log(`微信读书笔记迁移本地服务： http://localhost:${port}`));
async function serveAsset(request) { const url = new URL(request.url); let rel = decodeURIComponent(url.pathname).replace(/^\/+/, ""); if (!rel) rel = "index.html"; if (rel.includes("..") || rel.includes("\\")) return new Response("未找到", { status: 404 }); let file = path.join(dist, rel); try { const info = await stat(file); if (info.isDirectory()) file = path.join(file, "index.html"); return new Response(await readFile(file), { headers: { "content-type": mime(file) } }); } catch { return new Response(await readFile(path.join(dist, "index.html")), { headers: { "content-type": "text/html; charset=utf-8" } }); } }
function mime(file) { const ext = path.extname(file); return ({ ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json", ".txt": "text/plain; charset=utf-8" })[ext] ?? "application/octet-stream"; }
