import http from "node:http";
import { loadConfig } from "./platform/config.mjs";
import { PlatformStore } from "./platform/store.mjs";
import { createObjectStore } from "./platform/object-store.mjs";
import { PlatformService } from "./platform/service.mjs";
import { createPlatformApp } from "./platform/app.mjs";

const config = loadConfig();
const store = new PlatformStore(config.databasePath);
const objectStore = createObjectStore(config);
const service = new PlatformService({ store, objectStore, config });
const handle = createPlatformApp({ service, config });

const server = http.createServer(async (req, res) => {
  try {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) { size += chunk.length; if (size > config.maxImportBytes) { res.writeHead(413); res.end(); return; } chunks.push(chunk); }
    const url = `http://${req.headers.host || `${config.serviceHost}:${config.servicePort}`}${req.url || "/"}`;
    const request = new Request(url, { method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method || "GET") ? undefined : Buffer.concat(chunks), duplex: "half" });
    const response = await handle(request);
    const headers = {};
    response.headers.forEach((value, key) => { if (key === "set-cookie") headers[key] = response.headers.getSetCookie?.() || value; else headers[key] = value; });
    res.writeHead(response.status, headers);
    if (response.body) for await (const chunk of response.body) res.write(chunk);
    res.end();
  } catch { res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" }); res.end('{"error":{"code":"INTERNAL","message":"服务暂时不可用。"}}'); }
});
server.requestTimeout = 35_000;
server.headersTimeout = 10_000;
server.keepAliveTimeout = 5_000;
server.listen(config.servicePort, config.serviceHost, () => console.log(JSON.stringify({ event: "service_started", host: config.serviceHost, port: config.servicePort, version: "v0.0.0.1.8" })));
const shutdown = () => server.close(() => { store.close(); process.exit(0); });
process.on("SIGTERM", shutdown); process.on("SIGINT", shutdown);
