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

const { assertPublicEgress } = require("../privacy/public-egress");
const {
  SOURCE_URL,
  buildSourceOffer,
  renderSourcePage,
} = require("../release/source-offer");

// 挂在 response 上的出口路径。用 Symbol 是为了不和 node 自己的字段撞名。
const EGRESS_SURFACE = Symbol("cyberboss.egress.surface");
const SETUP_PATHS = Object.freeze(["/setup", "/setup/"]);
const ADMIN_PATHS = Object.freeze(["/admin", "/admin/"]);
// 只输一个域名就该看到东西。之前根路径落到最后那个 404 分支，用户看到的是一行
// {"ok":false,"code":"NOT_FOUND"}——服务其实好好的，却像是彻底坏了。
const ROOT_PATHS = Object.freeze(["/", "/index.html"]);
// R19 规定的 Owner 私有激活路由。和公开入口严格分开：公开入口给普通用户扫，
// 这里给主人扫 iLink 授权码，两者不共用任何一个 URL。
const OPS_WECHAT_PATHS = Object.freeze(["/ops/wechat", "/ops/wechat/"]);
// 后台里碰真实用户数据的接口名单。它们和其它 /admin/api/ 走不同的鉴权：永远
// 要令牌，没有首次运行免令牌这一说。名单写死在这里而不是靠前缀猜，是为了让
// "又加了一个读聊天的接口却忘了改鉴权"变成改不动的事——不进名单就进不了这条路。
// trace 里有模型吐的字（reply delta 就是用户看到的那些话），ops 里有队列和
// 用量——两样都是运营数据，和对话栏一个级别，永远要令牌，不走首次免令牌。
const OWNER_ONLY_ADMIN_APIS = Object.freeze(["conversations", "persona", "insights", "trace", "ops"]);
const OPS_WECHAT_TEMPLATE = require("node:path").join(__dirname, "../../../templates/ops-wechat.html");
// 公开入口。这一页任何人都能打开，也**必须**任何人都能打开——它就是给陌生人
// 扫码用的。所以它上面一个字的运营信息都不能有：没有人数、没有用量、没有状态。
const JOIN_PATHS = Object.freeze(["/join", "/join/"]);
const JOIN_TEMPLATE = require("node:path").join(__dirname, "../../../templates/join.html");
// 公开落地页。根路径以前直接跳后台，陌生人一进来就撞在登录墙上。
const HOME_TEMPLATE = require("node:path").join(__dirname, "../../../templates/home.html");
// 每个人自己那一页。HTML 免令牌（页面本身不含任何人的数据），数据接口要会话，
// 而且**只回签发给那个会话的那一个人的东西**——鉴权在 personalSiteData 里按
// 会话解出来的 user_id 做，路径上不带任何身份参数，想改都改不了别人的。
// AGPL 第 13 条要求的对应源码入口（CB9-540 / AC-029）。
//
// 免鉴权是硬要求，不是方便：使用者是那些扫码进来聊天的人，把源码链接放在后台里
// 等于没放，因为他们永远看不到后台。
const SOURCE_PATHS = Object.freeze(["/source", "/source/"]);
// app/src/services/portal → app 的上两级，再上一级是 CyberBoss。
const PROJECT_ROOT = require("node:path").join(__dirname, "../../../..");

const ME_PATHS = Object.freeze(["/me", "/me/"]);

// HEAD 会被当成 GET 的那些路径：**只有页面，没有会产生副作用的接口**。
// /api/join 故意不在里面——它的 GET 会发一张新票。
const HEAD_READABLE_PATHS = Object.freeze([
  "/", "/index.html", "/join", "/join/", "/source", "/source/",
  "/admin", "/admin/", "/me", "/me/", "/healthz",
]);
const ME_TEMPLATE = require("node:path").join(__dirname, "../../../templates/me.html");
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
    adminOwnerClaim = null,
    adminOwnerBind = null,
    // 这三个读写真实聊天内容与语气设置。它们走 #handleOwnerOnlyApi，永远要令牌。
    adminConversations = null,
    adminTrace = null,
    adminOps = null,
    adminPersonaRead = null,
    adminPersonaWrite = null,
    adminInsights = null,
    // 后台会话。给了这三个就支持"登录一次，之后免令牌"。
    publicEntry = null,
    publicEntryStatus = null,
    // 加入页静默上报的时区（CB9-210）。漏在这里的后果就是上面那段注释说的：
    // app.js 注入了、路由也挂了，但 this.joinTimezoneSignal 是 undefined，
    // handler 里那句 typeof === "function" 判断直接跳过——线上一个时区都收
    // 不到，而 adapter 的 18 条单测全绿。第九次了。
    joinTimezoneSignal = null,
    // 一键上下线（SWITCH-1）。读一个、写一个。
    systemSwitchRead = null,
    systemSwitchWrite = null,
    // 线上 release id，印在对应源码页上（CB9-540 / AC-029）。
    //
    // **第十次。** 这一条我也是先在别处写好、再回来发现构造函数里没接——
    // 现象一模一样：路由挂了、页面出得来，只是「线上版本」那一格永远显示
    // unreleased，而使用者拿它去对公开源码时对不上。
    //
    // 上面那段注释数到第九次，我以为读过就不会再犯。没有用——读到的教训防不住
    // 按名字解构这件事，能防住的只有一条**从真实入口进来的测试**。这次是
    // cb9-540 里那条起真服务器传 releaseIdProvider 的测试抓到的。
    releaseIdProvider = null,
    adminSessionIssue = null,
    adminSessionVerify = null,
    adminSessionRevoke = null,
    // 每个人自己那一页。漏在这里的后果是整条路默默变成 404——构造函数是**按名
    // 字解构**的，注入方写了但这里没接，`this.personalSiteData` 就是 undefined，
    // 而 #handleMeData 见到 undefined 会回 404。这个仓在同一件事上栽过八次了。
    personalSiteLogin = null,
    personalSiteData = null,
    personalSiteSettings = null,
    ownerActivationStart = null,
    ownerActivationPoll = null,
    firstRunProvider = () => false,
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
    this.adminOwnerClaim = adminOwnerClaim;
    this.adminOwnerBind = adminOwnerBind;
    this.adminConversations = adminConversations;
    this.adminTrace = adminTrace;
    this.adminOps = adminOps;
    this.adminPersonaRead = adminPersonaRead;
    this.adminPersonaWrite = adminPersonaWrite;
    this.personalSiteLogin = personalSiteLogin;
    this.personalSiteData = personalSiteData;
    this.personalSiteSettings = personalSiteSettings;
    this.adminInsights = adminInsights;
    this.publicEntry = publicEntry;
    this.joinTimezoneSignal = joinTimezoneSignal;
    this.systemSwitchRead = systemSwitchRead;
    this.systemSwitchWrite = systemSwitchWrite;
    this.releaseIdProvider = releaseIdProvider;
    this.publicEntryStatus = publicEntryStatus;
    this.adminSessionIssue = adminSessionIssue;
    this.adminSessionVerify = adminSessionVerify;
    this.adminSessionRevoke = adminSessionRevoke;
    this.ownerActivationStart = ownerActivationStart;
    this.ownerActivationPoll = ownerActivationPoll;
    this.firstRunProvider = firstRunProvider;
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
  // 还没有主人时放行：那时库里没有任何用户、任何凭据、任何聊天记录，后台上
  // 唯一能做的事就是把自己绑成主人。绑上之后这里立刻恢复要令牌。
  #firstRun() {
    try {
      return this.firstRunProvider() === true;
    } catch {
      return false;
    }
  }

  // 定长比较，避免字符串比较的提前返回泄漏令牌前缀。
  #tokenMatches(request) {
    if (!this.adminToken) {
      return false;
    }
    const supplied = String(request.headers["x-admin-token"] || "");
    const a = Buffer.from(supplied);
    const b = Buffer.from(this.adminToken);
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  }

  // 已经登录过的那台设备。
  //
  // 「我不可能每次都有 token」——所以令牌只用来换一次会话，之后靠 cookie。
  // cookie 是 HttpOnly + Secure + SameSite=Strict，页面脚本读不到它，跨站也带
  // 不出去。会话必须属于主人：普通用户在 /setup 拿到的会话用的是同一张
  // web_sessions 表，如果这里不校验身份，一个普通用户的设置会话就能读到全部人
  // 的聊天记录。这一条由 adminSessionVerify 在上层判定（它知道谁是主人）。
  #sessionAuthorized(request) {
    if (typeof this.adminSessionVerify !== "function") {
      return false;
    }
    try {
      return this.adminSessionVerify(String(request.headers.cookie || "")) === true;
    } catch {
      return false;
    }
  }

  #adminAuthorized(request) {
    if (this.#sessionAuthorized(request)) {
      return true;
    }
    if (this.#firstRun()) {
      return true;
    }
    return this.#tokenMatches(request);
  }

  // 所有 JSON 响应的**唯一**出口，隐私闸就装在这里（CB9-520 / AC-043）。
  //
  // 装在这里而不是各个处理函数里，是因为「每个处理函数记得调一下过滤器」是
  // 行为保证——写的时候都记得，下一个人加一条路由就漏了，而漏了没有任何症状。
  // 装在出口上就变成结构保证：往公开面塞脏东西这件事做不到，不需要谁记得。
  //
  // 出口路径从 response 上读（#route 挂的），用来挑那几个完全不鉴权的出口额外
  // 钉顶层键白名单。
  #json(response, status, payload) {
    const surface = response?.[EGRESS_SURFACE] || null;
    let body = payload;
    try {
      assertPublicEgress(payload, { surface });
    } catch (error) {
      // fail-closed：查出泄漏就**不发这份 payload**，而不是脱敏之后接着发。
      // 脱敏接着发会把上游那个 bug 藏起来——那一版代码依然在往公开面塞脏东西，
      // 只是这一层每次都在替它擦。
      body = { ok: false, code: "RESPONSE_WITHHELD" };
      status = 500;
      // 日志只记 code 和路径，**不记值**——记值的话这条日志本身就是那次泄漏，
      // 而且它落在普通日志里，泄漏面比原来更大。
      console.error(
        "[cyberboss] 响应被隐私闸拦下 出口=%s 原因=%s 位置=%s",
        surface || "(other)", error?.code || "EGRESS_UNKNOWN", error?.pointer || "$",
      );
    }
    response.writeHead(status, { ...SECURITY_HEADERS, "Content-Type": "application/json" });
    response.end(JSON.stringify(body));
  }

  // 「主页」那条链接里的票**就是会话本身**（web_sessions 本来就按 user_id 存）。
  // 这里只做一件事：把它从 URL 片段里换成一个 cookie，之后这台手机直接打开就行。
  async #handleMeLogin(request, response) {
    if (request.method !== "POST" || typeof this.personalSiteLogin !== "function") {
      this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
      return;
    }
    let token = "";
    try {
      const raw = await readBody(request);
      if (raw.length) {
        token = String(JSON.parse(raw.toString("utf8"))?.token || "");
      }
    } catch {
      token = "";
    }
    const result = this.personalSiteLogin(token);
    if (!result?.ok) {
      // 不区分"票过期"和"票是编的"，两者都只回一句拒绝。
      this.#json(response, 401, { ok: false, code: "LINK_INVALID" });
      return;
    }
    response.writeHead(200, {
      ...SECURITY_HEADERS,
      "Content-Type": "application/json",
      "Set-Cookie": result.cookie,
    });
    response.end(JSON.stringify({ ok: true }));
  }

  // 这一页的数据。**身份只从 cookie 里的会话解**，路径和 query 里没有任何
  // 用户参数——这样"看到别人的"不是一个需要防住的攻击，而是一件写不出来的事。
  // 对应源码页。
  //
  // 算摘要要读一遍源码树，所以缓存住——但只缓存**这个进程这一次运行**内的结果，
  // 不落盘：落盘的话换了 release 而缓存还在，页面会印着上一版的摘要，
  // 而那正是这一页最不该说错的东西。
  #handleSourceOffer(response) {
    try {
      if (!this.sourceOfferCache) {
        this.sourceOfferCache = buildSourceOffer({
          projectRoot: PROJECT_ROOT,
          releaseId: typeof this.releaseIdProvider === "function"
            ? this.releaseIdProvider()
            : null,
        });
      }
      const html = renderSourcePage(this.sourceOfferCache);
      response.writeHead(200, {
        ...SECURITY_HEADERS,
        "Content-Type": "text/html; charset=utf-8",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
      });
      response.end(html);
    } catch (error) {
      // 这一页失败不能是 404——404 读起来像「这个服务不提供源码」，而那是
      // 一句关于许可证的错话。500 加上仓库地址至少让人还能拿到源码。
      response.writeHead(500, { ...SECURITY_HEADERS, "Content-Type": "text/plain; charset=utf-8" });
      response.end(`对应源码页暂时算不出来，源码在 ${SOURCE_URL}\n`);
    }
    return null;
  }

  // 一键上下线：GET 读当前状态，POST 改。
  async #handleSystemSwitch(request, response) {
    // 和后台对话/语气同一条鉴权：会话 cookie 或管理员令牌，两者有其一。
    if (!this.#sessionAuthorized(request) && !(this.adminToken && this.#tokenMatches(request))) {
      this.#json(response, 401, { ok: false, code: "ADMIN_TOKEN_INVALID" });
      return null;
    }
    if (request.method === "GET") {
      if (typeof this.systemSwitchRead !== "function") {
        this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
        return null;
      }
      this.#json(response, 200, { ok: true, switch: this.systemSwitchRead() });
      return null;
    }
    if (request.method !== "POST" || typeof this.systemSwitchWrite !== "function") {
      this.#json(response, 405, { ok: false, code: "METHOD_NOT_ALLOWED" });
      return null;
    }
    let online;
    try {
      const raw = await readBody(request);
      const body = JSON.parse(raw.toString("utf8") || "{}");
      online = body.online;
    } catch {
      this.#json(response, 400, { ok: false, code: "BODY_INVALID" });
      return null;
    }
    // 只认真正的布尔值。收 "false" 这个字符串会被 JS 当成真——
    // 那意味着主人点「停」而系统听成了「开」，是这个接口最不能犯的错。
    if (typeof online !== "boolean") {
      this.#json(response, 400, { ok: false, code: "SWITCH_STATE_REQUIRED" });
      return null;
    }
    this.#json(response, 200, { ok: true, switch: this.systemSwitchWrite({ online }) });
    return null;
  }

  #handleMeData(request, response) {
    if (typeof this.personalSiteData !== "function") {
      this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
      return;
    }
    const data = this.personalSiteData(String(request.headers.cookie || ""));
    if (!data?.ok) {
      this.#json(response, 401, { ok: false, code: "SESSION_REQUIRED" });
      return;
    }
    this.#json(response, 200, data);
  }

  // 改自己的设置（现在只有「主动找我」）。身份同样只从 cookie 解，请求体里改不了
  // 别人的——越权在这里也是一件写不出来的事。
  //
  // 不带 CSRF token：cookie 是 SameSite=Strict，跨站请求根本带不上它。这和
  // adminSessionValid 那边（app.js 里 requireCsrf:false 的那处）是同一个判断。
  async #handleMeSettings(request, response) {
    if (request.method !== "POST" || typeof this.personalSiteSettings !== "function") {
      this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
      return;
    }
    let patch = {};
    try {
      const raw = await readBody(request);
      if (raw.length) {
        patch = JSON.parse(raw.toString("utf8")) || {};
      }
    } catch {
      patch = {};
    }
    const result = this.personalSiteSettings(String(request.headers.cookie || ""), patch);
    if (!result?.ok) {
      this.#json(response, 401, { ok: false, code: "SESSION_REQUIRED" });
      return;
    }
    this.#json(response, 200, result);
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
      if (
        name === "owner-bind"
        && request.method === "POST"
        && typeof this.adminOwnerBind === "function"
      ) {
        this.#json(response, 200, await this.adminOwnerBind());
        return;
      }
      if (name === "first-run") {
        this.#json(response, 200, { ok: true, firstRun: this.#firstRun() });
        return;
      }
      if (
        name === "owner-claim"
        && request.method === "POST"
        && typeof this.adminOwnerClaim === "function"
      ) {
        this.#json(response, 200, await this.adminOwnerClaim());
        return;
      }
    } catch (error) {
      this.logger.warn?.(`[cyberboss] 后台 ${name} 失败 code=${error?.code || "unknown"}`);
      this.#json(response, 500, { ok: false, code: "ADMIN_ACTION_FAILED" });
      return;
    }
    this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
  }

  // 登录：把一次性的东西换成一个长期的会话 cookie。
  //
  // 两种入场券，都只用一次：
  //   · x-admin-token —— 服务器管理者手上的长期令牌（部署时生成）
  //   · ticket        —— 微信里发「后台」拿到的一次性票，5 分钟有效
  //
  // 换完之后页面就只靠 cookie 了，令牌不再需要出现在任何地方。
  async #handleAdminLogin(request, response) {
    if (request.method !== "POST" || typeof this.adminSessionIssue !== "function") {
      this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
      return;
    }
    let ticket = "";
    try {
      const raw = await readBody(request);
      if (raw.length) {
        const parsed = JSON.parse(raw.toString("utf8"));
        ticket = typeof parsed?.ticket === "string" ? parsed.ticket.slice(0, 128) : "";
      }
    } catch {
      ticket = "";
    }
    const byToken = Boolean(this.adminToken) && this.#tokenMatches(request);
    // 第三种：已经登录着，来续期。页面每次打开都会做一次，所以常用的那台设备
    // 不会因为会话上限（24 小时）而掉线。
    const renewFrom = !byToken && !ticket && this.#sessionAuthorized(request)
      ? String(request.headers.cookie || "")
      : "";
    if (!byToken && !ticket && !renewFrom) {
      this.#json(response, 401, { ok: false, code: "ADMIN_TOKEN_INVALID" });
      return;
    }
    let issued;
    try {
      issued = await this.adminSessionIssue({ ticket: byToken ? "" : ticket, renewFrom });
    } catch (error) {
      this.logger.warn?.(`[cyberboss] 后台登录失败 code=${error?.code || "unknown"}`);
      this.#json(response, 401, { ok: false, code: "ADMIN_LOGIN_FAILED" });
      return;
    }
    if (!issued || !issued.ok) {
      this.#json(response, 401, { ok: false, code: issued?.code || "ADMIN_LOGIN_FAILED" });
      return;
    }
    response.writeHead(200, {
      ...SECURITY_HEADERS,
      "Content-Type": "application/json",
      "Set-Cookie": issued.setCookie,
    });
    // csrf 回给页面用于后续写操作；会话令牌本身在 HttpOnly cookie 里，页面看不到。
    response.end(JSON.stringify({ ok: true, csrf: issued.csrf, expiresAt: issued.expiresAt }));
  }

  // 公开入口。没有鉴权是刻意的：这一页就是给陌生人看的。
  // 它只吐一张现要的二维码和一句中文；出错也只说"还没准备好"，不把内部错误码
  // 吐到公开页上。
  async #handlePublicEntry(response) {
    let payload = {
      ok: true, ready: false, status: "pending_activation",
      message: "这个机器人还没准备好，请稍后再来。",
    };
    try {
      payload = (typeof this.publicEntry === "function" ? await this.publicEntry() : null) || payload;
    } catch {
      // 保持默认那句。
    }
    this.#json(response, 200, payload);
    return null;
  }

  async #handlePublicEntryStatus(response, ticket) {
    let payload = { ok: true, state: "wait", message: "" };
    try {
      payload = (typeof this.publicEntryStatus === "function"
        ? await this.publicEntryStatus(String(ticket || ""))
        : null) || payload;
    } catch {
      // 同上：公开页只看得到状态词。
    }
    this.#json(response, 200, payload);
    return null;
  }

  // 这个接口**永远**回 200 ok。
  //
  // 时区是锦上添花：有它回复更贴人，没它回退北京时间照样能聊。让一次上报失败
  // 变成页面上一个错误、或者让访客卡在扫码前，就是拿主路径去赌一个可降级的字
  // 段——AC-012 明说「无任何信号时首条回复仍成功」，AC-042 明说不阻塞扫码。
  // 所以这里连 4xx 都不回：调用方没有任何需要分支处理的失败态。
  async #handleJoinTimezone(request, response) {
    let timezone = "";
    let ticket = "";
    try {
      const raw = await readBody(request);
      if (raw.length) {
        const body = JSON.parse(raw.toString("utf8"));
        timezone = String(body?.timezone || "");
        ticket = String(body?.ticket || "");
      }
    } catch {
      // body 坏了就当没报过。
    }
    try {
      if (typeof this.joinTimezoneSignal === "function") {
        await this.joinTimezoneSignal({ ticket, timezone, headers: request.headers });
      }
    } catch {
      // 采集出任何岔子都不许影响加入。
    }
    this.#json(response, 200, { ok: true });
    return null;
  }

  async #handleAdminLogout(request, response) {
    if (request.method !== "POST") {
      this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
      return;
    }
    let cleared = "";
    try {
      cleared = typeof this.adminSessionRevoke === "function"
        ? await this.adminSessionRevoke(String(request.headers.cookie || ""))
        : "";
    } catch {
      cleared = "";
    }
    const headers = { ...SECURITY_HEADERS, "Content-Type": "application/json" };
    if (cleared) {
      headers["Set-Cookie"] = cleared;
    }
    response.writeHead(200, headers);
    response.end(JSON.stringify({ ok: true }));
  }

  // 后台里真正碰用户数据的那几个接口。
  //
  // 和 #handleAdminApi 的区别只有一条，但那一条是全部：**不走首次运行免令牌**。
  // 概览页免令牌是安全的——还没有主人时库里没有任何用户数据。但对话一栏读的是
  // 解密后的真实聊天，语气一栏改的是每个人都会收到的说话方式，这两件事在任何
  // 时候都必须先证明你是服务器的管理者。
  async #handleOwnerOnlyApi(request, response, name, url) {
    // 会话或令牌，二者其一。**不接受**首次运行免令牌——那条规则只对概览成立。
    if (!this.#sessionAuthorized(request) && !(this.adminToken && this.#tokenMatches(request))) {
      this.#json(response, 401, { ok: false, code: "ADMIN_TOKEN_INVALID" });
      return;
    }
    try {
      if (name === "conversations" && typeof this.adminConversations === "function") {
        // 每个参数都在这里定长截断。它们最终会进 SQL 的绑定参数和内存比较，
        // 不会被拼进语句，但一个没有上限的关键词照样能把一次查询拖垮。
        const bounded = (key, max) => String(url.searchParams.get(key) || "").slice(0, max);
        this.#json(response, 200, await this.adminConversations({
          limit: Number(url.searchParams.get("limit")) || 40,
          person: bounded("person", 200),
          keyword: bounded("q", 120),
          from: bounded("from", 32),
          to: bounded("to", 32),
        }));
        return;
      }
      // 这一轮它当时一步步在干什么。给 job 或 turn 其中之一。
      if (name === "trace" && typeof this.adminTrace === "function") {
        this.#json(response, 200, await this.adminTrace({
          jobId: String(url.searchParams.get("job") || "").slice(0, 120),
          turnId: String(url.searchParams.get("turn") || "").slice(0, 120),
        }));
        return;
      }
      if (name === "ops" && typeof this.adminOps === "function") {
        this.#json(response, 200, await this.adminOps());
        return;
      }
      if (name === "insights" && typeof this.adminInsights === "function") {
        this.#json(response, 200, await this.adminInsights({
          person: String(url.searchParams.get("person") || "").slice(0, 200),
          days: Number(url.searchParams.get("days")) || 120,
        }));
        return;
      }
      if (name === "persona" && request.method === "GET" && typeof this.adminPersonaRead === "function") {
        // person 给了就读那个人自己的语气，不给就是主人那一行（所有人的默认值）。
        this.#json(response, 200, await this.adminPersonaRead({
          person: String(url.searchParams.get("person") || "").slice(0, 200),
        }));
        return;
      }
      if (name === "persona" && request.method === "POST" && typeof this.adminPersonaWrite === "function") {
        const raw = await readBody(request);
        let input = {};
        try {
          input = raw.length ? JSON.parse(raw.toString("utf8")) : {};
        } catch {
          this.#json(response, 400, { ok: false, code: "PERSONA_BODY_INVALID" });
          return;
        }
        this.#json(response, 200, await this.adminPersonaWrite(input));
        return;
      }
    } catch (error) {
      // 只记码。这条路上的 body 是真实聊天内容和主人写的语气，一个字都不进日志。
      this.logger.warn?.(`[cyberboss] 后台 ${name} 失败 code=${error?.code || "unknown"}`);
      this.#json(response, 500, { ok: false, code: "ADMIN_ACTION_FAILED" });
      return;
    }
    this.#json(response, 404, { ok: false, code: "NOT_FOUND" });
  }

  async #handleOwnerActivation(request, response, name, url) {
    // 这里**不走**首次运行免令牌那条规则。
    //
    // 后台首次免令牌是安全的：那时库里没有用户、没有凭据、没有聊天记录，页面上
    // 唯一能做的事就是把自己绑成主人。但这个路由不一样——它能发起一次真实的微信
    // 授权，谁先扫谁的微信就成了机器人号。所以无论首次与否，一律要令牌。
    if (!this.adminToken || !this.#tokenMatches(request)) {
      this.#json(response, 401, { ok: false, code: "ADMIN_TOKEN_INVALID" });
      return;
    }
    try {
      if (name === "start" && request.method === "POST" && typeof this.ownerActivationStart === "function") {
        this.#json(response, 200, await this.ownerActivationStart());
        return;
      }
      if (name === "poll" && typeof this.ownerActivationPoll === "function") {
        this.#json(response, 200, await this.ownerActivationPoll(url.searchParams.get("qrcode") || ""));
        return;
      }
    } catch (error) {
      this.logger.warn?.(`[cyberboss] ops/wechat ${name} 失败 code=${error?.code || "unknown"}`);
      this.#json(response, 500, { ok: false, code: "OWNER_ACTIVATION_FAILED" });
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
    // 把出口路径挂在 response 上，#json 自己去读。
    //
    // 不让每个处理函数把 pathname 传给 #json：那又变成「记得传」的行为保证，
    // 而漏传的那一条恰好就是新加的那条路由——最可能出问题的那一条。
    // 一个请求对应一个 response 对象，所以并发下不会串。
    response[EGRESS_SURFACE] = pathname;

    // HEAD 当 GET 走——但只对纯读的那几条路径。
    //
    // 起因是 2026-08-02 在真站上量出来的：**每一个**公开路径 HEAD 都回 404，
    // 包括 /healthz。而探活监控普遍默认用 HEAD，于是它会一直报「站挂了」，
    // 而站是好的。这正是这套系统最不该犯的那种错——面板指着一个不存在的
    // 故障，指多了，真出事那天就没人当回事了。
    //
    // 不无脑把所有 HEAD 都当 GET：/api/join 的 GET 会**发一张新票**。让 HEAD
    // 也能发票，等于多了一条不留正文痕迹的方式去消耗票池。监控探的是页面，
    // 不是发票接口，所以名单只列页面。
    //
    // 正文不用自己截断：Node 对 HEAD 请求的 response 不会发送 body。
    const method = (request.method === "HEAD" && HEAD_READABLE_PATHS.includes(pathname))
      ? "GET"
      : request.method;

    if (method === "GET" && ROOT_PATHS.includes(pathname)) {
      // 以前这里是 302 跳 /admin。陌生人打开这个域名，看到的是主人的后台登录页
      // ——对一个要卖出去的产品来说，那等于把大门开在员工通道上，而且他连
      // 「怎么开始用」的入口都找不到。
      //
      // 现在给一页公开的落地页：一个大按钮去 /join，底下一行小字给管理员。
      // 和 /join 一样免鉴权，因为它同样一个字的运营信息都没有。
      const nonce = newNonce();
      const html = fs.readFileSync(HOME_TEMPLATE, "utf8").replaceAll("__CSP_NONCE__", nonce);
      response.writeHead(200, { ...SECURITY_HEADERS, "Content-Type": "text/html; charset=utf-8" });
      response.end(html);
      return null;
    }
    if (request.method === "GET" && OPS_WECHAT_PATHS.includes(pathname)) {
      // 页面本身不含任何凭据，和后台页同样处理：HTML 免令牌，数据接口要令牌。
      const nonce = newNonce();
      const html = fs.readFileSync(OPS_WECHAT_TEMPLATE, "utf8").replaceAll("__CSP_NONCE__", nonce);
      response.writeHead(200, { ...SECURITY_HEADERS, "Content-Type": "text/html; charset=utf-8" });
      response.end(html);
      return null;
    }
    if (pathname.startsWith("/ops/api/wechat/")) {
      return this.#handleOwnerActivation(request, response, pathname.slice("/ops/api/wechat/".length), url);
    }
    if (method === "GET" && ADMIN_PATHS.includes(pathname)) {
      this.#handleAdminPage(response);
      return null;
    }
    // 公开入口：无鉴权，这是刻意的。它只吐一张二维码和一句说明。
    if (method === "GET" && JOIN_PATHS.includes(pathname)) {
      const nonce = newNonce();
      const html = fs.readFileSync(JOIN_TEMPLATE, "utf8").replaceAll("__CSP_NONCE__", nonce);
      response.writeHead(200, { ...SECURITY_HEADERS, "Content-Type": "text/html; charset=utf-8" });
      response.end(html);
      return null;
    }
    if (request.method === "GET" && pathname === "/api/join") {
      return this.#handlePublicEntry(response);
    }
    // 每个人自己那一页。页面免令牌（它本身不含任何人的数据），数据要会话。
    // 对应源码那一页。放在鉴权分支**之前**——AC-029 要「链接对未登录网络用户
    // 可见」，而 AGPL 第 13 条不接受「先登录再说」。
    if (method === "GET" && SOURCE_PATHS.includes(pathname)) {
      return this.#handleSourceOffer(response);
    }
    if (method === "GET" && ME_PATHS.includes(pathname)) {
      const nonce = newNonce();
      const html = fs.readFileSync(ME_TEMPLATE, "utf8").replaceAll("__CSP_NONCE__", nonce);
      response.writeHead(200, {
        ...SECURITY_HEADERS,
        "Content-Type": "text/html; charset=utf-8",
        "Content-Security-Policy": `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
      });
      response.end(html);
      return null;
    }
    if (pathname === "/me/api/login") {
      return this.#handleMeLogin(request, response);
    }
    if (pathname === "/me/api/settings") {
      return this.#handleMeSettings(request, response);
    }
    if (request.method === "GET" && pathname === "/me/api/data") {
      return this.#handleMeData(request, response);
    }
    // 扫码进度。只回 wait / scaned / confirmed / expired 四种状态和一句中文，
    // 不回 accountId、不回 token、不回任何人的身份。
    if (request.method === "GET" && pathname === "/api/join/status") {
      return this.#handlePublicEntryStatus(response, url.searchParams.get("t") || "");
    }
    // 加入页静默上报浏览器 IANA 时区（CB9-210 / AC-012）。
    // 和公开页同样无鉴权——它收的东西比公开页还少：一个时区名，绑在一张我们
    // 自己发出去的票上。
    if (request.method === "POST" && pathname === "/api/join/timezone") {
      return this.#handleJoinTimezone(request, response);
    }
    if (pathname === "/admin/api/login") {
      return this.#handleAdminLogin(request, response);
    }
    if (pathname === "/admin/api/logout") {
      return this.#handleAdminLogout(request, response);
    }
    // 顺序要紧：这一条必须排在 /admin/api/ 的通用分支前面，否则对话和语气会掉
    // 进 #handleAdminApi，跟着继承首次运行免令牌那条规则。
    // 一键上下线。**必须是主人专属**——任何人能按的开关等于任何人都能让
    // 整套系统停摆。走和对话/语气同一条鉴权路径。
    if (pathname === "/admin/api/system-switch") {
      return this.#handleSystemSwitch(request, response);
    }
    if (OWNER_ONLY_ADMIN_APIS.some((name) => pathname === `/admin/api/${name}`)) {
      return this.#handleOwnerOnlyApi(
        request,
        response,
        pathname.slice("/admin/api/".length),
        url,
      );
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
    if (method === "GET" && pathname === "/healthz") {
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
