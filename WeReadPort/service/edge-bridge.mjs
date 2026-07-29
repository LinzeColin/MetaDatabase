/**
 * Private bridge between the Coolify Traefik container and the loopback-only
 * account platform.  It deliberately never listens on a public interface.
 */
import http from "node:http";
import net from "node:net";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HOP_BY_HOP_HEADERS = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
]);
const MAX_UPSTREAM_TIMEOUT_MS = 52_000;

export function parseEdgeBridgeConfig(env = process.env) {
  const listenHost = String(env.WRP_EDGE_BRIDGE_HOST || "").trim();
  const listenPort = positivePort(env.WRP_EDGE_BRIDGE_PORT || "8789", "WRP_EDGE_BRIDGE_PORT");
  const upstreamHost = String(env.WRP_SERVICE_HOST || "127.0.0.1").trim();
  const upstreamPort = positivePort(env.WRP_SERVICE_PORT || "8788", "WRP_SERVICE_PORT");
  if (!isPrivateIpv4(listenHost)) throw new Error("WRP_EDGE_BRIDGE_HOST 必须是 RFC1918 Docker 私网 IPv4 地址。");
  if (!isLoopback(upstreamHost)) throw new Error("WRP_SERVICE_HOST 必须继续是回环地址。");
  return Object.freeze({
    listenHost,
    listenPort,
    upstreamHost,
    upstreamPort,
    peerPrefix: listenHost.split(".").slice(0, 3).join(".") + ".",
  });
}

export function createEdgeBridge(config, { httpModule = http, peerAllowed = defaultPeerAllowed } = {}) {
  if (!config || !isPrivateIpv4(config.listenHost) || !isLoopback(config.upstreamHost)) throw new Error("EDGE_BRIDGE_CONFIG_INVALID");
  return httpModule.createServer((request, response) => {
    const remoteAddress = normalizeAddress(request.socket.remoteAddress);
    if (!peerAllowed(remoteAddress, config)) {
      request.resume();
      response.writeHead(403, { "cache-control": "no-store", "content-type": "application/json; charset=utf-8" });
      response.end('{"error":{"code":"EDGE_PEER_DENIED","message":"访问来源不被允许。"}}');
      return;
    }
    const upstream = httpModule.request({
      host: config.upstreamHost,
      port: config.upstreamPort,
      method: request.method,
      path: request.url || "/",
      headers: withoutHopByHopHeaders(request.headers),
    }, upstreamResponse => {
      response.writeHead(upstreamResponse.statusCode || 502, withoutHopByHopHeaders(upstreamResponse.headers));
      upstreamResponse.pipe(response);
    });
    upstream.setTimeout(MAX_UPSTREAM_TIMEOUT_MS, () => upstream.destroy(new Error("EDGE_UPSTREAM_TIMEOUT")));
    upstream.once("error", () => {
      if (response.headersSent) response.destroy();
      else {
        response.writeHead(502, { "cache-control": "no-store", "content-type": "application/json; charset=utf-8" });
        response.end('{"error":{"code":"EDGE_UPSTREAM_UNAVAILABLE","message":"账户服务暂时不可用，请稍后重试。"}}');
      }
    });
    request.once("aborted", () => upstream.destroy());
    request.pipe(upstream);
  });
}

function positivePort(value, name) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) throw new Error(`${name} 必须是 1–65535 的整数。`);
  return port;
}

function isLoopback(value) { return value === "127.0.0.1" || value === "::1" || value === "localhost"; }

function isPrivateIpv4(value) {
  if (net.isIP(value) !== 4) return false;
  const [first, second] = value.split(".").map(Number);
  return first === 10 || (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 168);
}

function normalizeAddress(value) {
  const raw = String(value || "");
  return raw.startsWith("::ffff:") ? raw.slice(7) : raw;
}

function defaultPeerAllowed(remoteAddress, config) {
  return net.isIP(remoteAddress) === 4 && remoteAddress.startsWith(config.peerPrefix);
}

function withoutHopByHopHeaders(headers) {
  const clean = {};
  const connectionHeaders = new Set(String(headers?.connection || "").split(",").map(item => item.trim().toLowerCase()).filter(Boolean));
  for (const [name, value] of Object.entries(headers || {})) {
    if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase()) && !connectionHeaders.has(name.toLowerCase()) && value !== undefined) clean[name] = value;
  }
  return clean;
}

function start() {
  const config = parseEdgeBridgeConfig();
  const server = createEdgeBridge(config);
  server.requestTimeout = 55_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 5_000;
  server.listen(config.listenPort, config.listenHost, () => {
    console.log(JSON.stringify({ event: "edge_bridge_started", listenHost: config.listenHost, listenPort: config.listenPort, upstreamHost: config.upstreamHost, upstreamPort: config.upstreamPort }));
  });
  const shutdown = () => server.close(() => process.exit(0));
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) start();
