"use strict";

// 真正对外提供设置页面的那台 HTTP 服务。
//
// 它**只**监听 127.0.0.1。公网入口由 Cloudflare Tunnel 提供：cloudflared 从这
// 台机器主动向外建连，所以路由器和防火墙上不需要开任何入站端口，也没有一个
// 直接暴露在公网上的监听口。这是比"开个 443 再自己管证书"更小的攻击面，也是
// TaskPack 里写明的部署形态。
//
// 这一层只做三件事：路由、读 body、把响应写回去。所有安全判定——Host、Origin、
// action 白名单、body 上限、session、CSRF——都在 SetupPortal 里，这里一件都不
// 重复实现，因为两份略有出入的实现就是漏洞的来源。

const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");

const { PortalError, renderSetupPage } = require("./setup-portal");

const DASHBOARD_TEMPLATE = require("node:path").join(
  __dirname,
  "../../../templates/dashboard.html",
);

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8787;
const API_PREFIX = "/api/";
const SETUP_PATHS = Object.freeze(["/setup", "/setup/"]);
const ADMIN_PATHS = Object.freeze(["/admin", "/admin/"]);
// 读 body 的硬上限。SetupPortal 自己还会再判一次 16 KiB；这里的作用是让一个
// 无限长的请求在耗尽内存之前就被切断。
const MAX_REQUEST_BYTES = 64 * 1024;
const REQUEST_TIMEOUT_MS = 15_000;

const SECURITY_HEADERS = Object.freeze({
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
  "Cache-Control": "no-store",
});

function newNonce() {
  return crypto.randomBytes(18).toString("base64url");
}

function readBody(request, limit = MAX_REQUEST_BYTES) {
  // 声明的长度就超了的话，一个字节都不用读。
  const declared = Number(request.headers["content-length"]);
  if (Number.isFinite(declared) && declared > limit) {
    return Promise.reject(new PortalError("BODY_TOO_LARGE", 413));
  }
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    let settled = false;
    request.on("data", (chunk) => {
      if (settled) {
        return;
      }
      size += chunk.length;
      if (size > limit) {
        // 只停止累积并如实回 413。这里不 destroy：把连接直接掐掉，客户端看到
        // 的是 ECONNRESET，而它其实有资格知道自己是被拒绝了、以及为什么。
        settled = true;
        reject(new PortalError("BODY_TOO_LARGE", 413));
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      if (!settled) {
        settled = true;
        resolve(Buffer.concat(chunks));
      }
    });
    request.on("error", (error) => {
      if (!settled) {
        settled = true;
        reject(error);
      }
    });
  });
}

// 错误回给浏览器时只带状态码和错误码，不带堆栈也不带任何用户数据。
function errorBody(error) {
  const code = error && typeof error.code === "string" ? error.code : "PORTAL_ERROR";
  const status = Number.isInteger(error?.status) ? error.status : 500;
  return { status, payload: { ok: false, code } };
}

class PortalHttpServer {
  constructor({
    portal,
    host = DEFAULT_HOST,
    port = DEFAULT_PORT,
    usageProvider = () => 100,
    // 后台数据由外面注入：这一层只管路由和鉴权，不知道业务是怎么算出来的。
    adminToken = "",
    adminOverview = null,
    adminInvite = null,
    logger = console,
  }) {
    if (!portal || typeof portal.handle !== "function") {
      throw new TypeError("portal is required");
    }
    this.portal = portal;
    this.host = host;
    this.port = port;
    this.usageProvider = usageProvider;
    this.adminToken = typeof adminToken === "string" ? adminToken : "";
    this.adminOverview = adminOverview;
    this.adminInvite = adminInvite;
    this.logger = logger;
    this.server = null;
  }

  #handleSetupPage(response) {
    const nonce = newNonce();
    let remaining = 100;
    try {
      remaining = Number(this.usageProvider()) || 0;
    } catch {
      // 读不到用量就按满额显示：这只是页面上的一个进度条，真正的限额判定在
      // 每次模型调用之前由预算守卫做。
      remaining = 100;
    }
    const html = renderSetupPage({ nonce, remainingPercent: remaining });
    response.writeHead(200, {
      ...SECURITY_HEADERS,
      "Content-Type": "text/html; charset=utf-8",
    });
    response.end(html);
  }

  async #handleApi(request, response, action) {
    let body;
    try {
      body = await readBody(request);
    } catch (error) {
      const { status, payload } = errorBody(error);
      response.writeHead(status, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
      // 回完 413 之后再收连接：客户端先拿到答案，剩下没发完的字节直接丢弃，
      // 不会为了读完一个已经被拒绝的请求继续占内存。
      response.end(JSON.stringify(payload), () => request.destroy());
      return;
    }

    let result;
    try {
      result = this.portal.handle({
        method: request.method,
        action,
        headers: request.headers,
        body: body.length ? body : null,
      });
    } catch (error) {
      const { status, payload } = errorBody(error);
      // 记录码，不记录 body、不记录 cookie、不记录任何用户标识。
      this.logger.warn?.(`[cyberboss] portal ${action} refused code=${payload.code}`);
      response.writeHead(status, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
      response.end(JSON.stringify(payload));
      return;
    }

    const headers = { ...SECURITY_HEADERS, "Content-Type": "application/json" };
    // session.exchange 是唯一会发 cookie 的动作，cookie 串由 session 服务生成，
    // 这里原样透传，不重新拼装。
    if (result && typeof result.setCookie === "string") {
      headers["Set-Cookie"] = result.setCookie;
    }
    const { setCookie: _omitted, ...safe } = result || {};
    response.writeHead(Number.isInteger(result?.status) ? result.status : 200, headers);
    response.end(JSON.stringify({ ok: true, ...safe }));
  }

  // 定长比较，避免用字符串比较的提前返回泄漏令牌前缀。
  #adminAuthorized(request) {
    if (!this.adminToken) {
      return false;
    }
    const supplied = String(request.headers["x-admin-token"] || "");
    const a = Buffer.from(supplied);
    const b = Buffer.from(this.adminToken);
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  }

  #json(response, status, payload) {
    response.writeHead(status, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
    response.end(JSON.stringify(payload));
  }

  async #handleAdminApi(request, response, name) {
    if (!this.#adminAuthorized(request)) {
      // 不区分"令牌错"和"功能没开"，两者都只回一句拒绝。
      this.#json(response, 401, { ok: false, code: "ADMIN_TOKEN_INVALID" });
      return;
    }
    try {
      if (name === "overview" && typeof this.adminOverview === "function") {
        this.#json(response, 200, await this.adminOverview());
        return;
      }
      if (name === "invite" && request.method === "POST" && typeof this.adminInvite === "function") {
        this.#json(response, 200, await this.adminInvite());
        return;
      }
    } catch (error) {
      this.logger.warn?.(`[cyberboss] 后台 ${name} 失败 code=${error?.code || "unknown"}`);
      this.#json(response, 500, { ok: false, code: "ADMIN_ACTION_FAILED" });
      return;
    }
    this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
  }

  // 后台页面本身不含任何数据，所以不要令牌也能拿到 HTML；数据接口才要。
  #handleAdminPage(response) {
    const nonce = newNonce();
    const html = fs.readFileSync(DASHBOARD_TEMPLATE, "utf8").replaceAll("__CSP_NONCE__", nonce);
    response.writeHead(200, { ...SECURITY_HEADERS, "Content-Type": "text/html; charset=utf-8" });
    response.end(html);
  }

  #route(request, response) {
    const url = new URL(request.url || "/", "http://placeholder.invalid");
    const pathname = url.pathname;

    if (request.method === "GET" && ADMIN_PATHS.includes(pathname)) {
      this.#handleAdminPage(response);
      return null;
    }
    if (pathname.startsWith("/admin/api/")) {
      return this.#handleAdminApi(request, response, pathname.slice("/admin/api/".length));
    }
    if (request.method === "GET" && SETUP_PATHS.includes(pathname)) {
      this.#handleSetupPage(response);
      return null;
    }
    if (pathname.startsWith(API_PREFIX)) {
      // action 从路径里取，SetupPortal 会拿它去比对冻结白名单；这里不做任何
      // 前置放行。
      return this.#handleApi(request, response, decodeURIComponent(pathname.slice(API_PREFIX.length)));
    }
    // 健康检查故意不透露任何状态，只证明进程还活着。
    if (request.method === "GET" && pathname === "/healthz") {
      response.writeHead(200, { ...SECURITY_HEADERS, "Content-Type": "text/plain" });
      response.end("ok");
      return null;
    }
    response.writeHead(404, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
    response.end(JSON.stringify({ ok: false, code: "NOT_FOUND" }));
    return null;
  }

  start() {
    if (this.server) {
      return Promise.resolve(this.address());
    }
    this.server = http.createServer((request, response) => {
      response.setHeader("Connection", "close");
      try {
        const pending = this.#route(request, response);
        if (pending) {
          pending.catch((error) => {
            const { status, payload } = errorBody(error);
            if (!response.headersSent) {
              response.writeHead(status, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
            }
            response.end(JSON.stringify(payload));
          });
        }
      } catch (error) {
        const { status, payload } = errorBody(error);
        if (!response.headersSent) {
          response.writeHead(status, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
        }
        response.end(JSON.stringify(payload));
      }
    });
    this.server.requestTimeout = REQUEST_TIMEOUT_MS;
    this.server.headersTimeout = REQUEST_TIMEOUT_MS;
    return new Promise((resolve, reject) => {
      this.server.once("error", reject);
      this.server.listen(this.port, this.host, () => {
        this.server.removeListener("error", reject);
        resolve(this.address());
      });
    });
  }

  address() {
    const info = this.server?.address();
    return info ? Object.freeze({ host: info.address, port: info.port }) : null;
  }

  stop() {
    const server = this.server;
    if (!server) {
      return Promise.resolve();
    }
    this.server = null;
    return new Promise((resolve) => server.close(() => resolve()));
  }
}

module.exports = {
  API_PREFIX,
  DEFAULT_HOST,
  DEFAULT_PORT,
  MAX_REQUEST_BYTES,
  PortalHttpServer,
  SECURITY_HEADERS,
};
