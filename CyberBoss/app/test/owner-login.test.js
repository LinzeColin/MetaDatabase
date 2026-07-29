"use strict";

// 后台登录。
//
// 起因是一句用户原话：「我不可能每次都有 token」。把长期令牌塞在链接里、要人
// 每次粘贴，等于把服务器的钥匙交给剪贴板保管。所以令牌只用来换一次会话，之后
// 靠 cookie；cookie 掉了就在微信里说一句「后台」，拿一条一次性链接。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { bootstrapInstallation } = require("../src/core/bootstrap");
const { readConfig } = require("../src/core/config");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { PortalHttpServer } = require("../src/services/portal/portal-server");
const { SqliteAdminLoginTickets } = require("../src/services/security/admin-login-ticket");
const {
  SqliteSessionTokenService,
} = require("../src/services/security/session-token-service");
const { defaultPersona, normalizePersona } = require("../src/services/persona/persona-store");

const ENCRYPTION_KEY = Buffer.alloc(32, 41);
const IDENTITY_KEY = Buffer.alloc(32, 43);

function temporaryDirectory(t, prefix) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function openSpool(t, prefix) {
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(temporaryDirectory(t, prefix), "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  return spool;
}

// 真实的 CyberbossApp，和 `cyberboss start` 走同一条构造路径。
function bootApp(t) {
  const home = temporaryDirectory(t, "cb-login-app-");
  const stateDir = path.join(home, ".cyberboss");
  const saved = new Map();
  const set = (name, value) => {
    if (!saved.has(name)) saved.set(name, process.env[name]);
    if (value === null) delete process.env[name];
    else process.env[name] = value;
  };
  t.after(() => {
    for (const [name, value] of saved) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  });

  set("CYBERBOSS_STATE_DIR", stateDir);
  set("CYBERBOSS_WORKSPACE_CONFIG", path.join(stateDir, "workspaces.json"));
  set("CYBERBOSS_WORKSPACE_BASE", null);
  set("CYBERBOSS_WORKSPACE_ROOT", null);
  set("CB_DURABLE_INBOX", "true");
  set("CB_MULTI_USER", "true");
  set("CB_REGISTRATION_MODE", "invite");
  // 指名主人，否则第一个说话的人会自动认领主人——"outsider"就成了主人，
  // 那条隔离断言也就测不到东西了。
  set("CB_OWNER_SENDER_IDS", "owner-sender");
  set("CB_PORTAL_ORIGIN", "https://boss.example.com");
  set("CB_RUNTIME_DB", path.join(stateDir, "runtime.db"));
  set("CB_ALLOW_BASELINE_STAGING", "true");
  set("NODE_ENV", "test");
  set("CB_PRIVATE_DB_CANONICAL_SYNC", "false");

  const result = bootstrapInstallation({ stateDir });
  set("CB_RUNTIME_ENCRYPTION_KEY_FILE", result.encryptionKey.path);
  set("CB_RUNTIME_IDENTITY_KEY_FILE", result.identityKey.path);

  const app = new CyberbossApp(readConfig());
  app.initializeDurableInbox();
  t.after(() => app.runtimeSpoolDatabase?.close?.());
  return app;
}

function request(port, options = {}) {
  return new Promise((resolve, reject) => {
    const payload = options.body === undefined ? null : Buffer.from(options.body);
    const call = http.request(
      {
        host: "127.0.0.1",
        port,
        method: options.method || "GET",
        path: options.requestPath || "/",
        headers: {
          ...(options.headers || {}),
          ...(payload ? { "content-length": String(payload.length) } : {}),
        },
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let json = null;
          try {
            json = JSON.parse(text);
          } catch {
            json = null;
          }
          resolve({ status: response.statusCode, headers: response.headers, text, json });
        });
      },
    );
    call.on("error", reject);
    if (payload) call.write(payload);
    call.end();
  });
}

const cookieOf = (response) => String(response.headers["set-cookie"] || "").split(";")[0];

async function loginServer(t, { firstRun = false } = {}) {
  const spool = openSpool(t, "cb-login-srv-");
  // 用真实原型做接收者，而不是手挑几个方法挂上去：issueAdminSession 内部会调
  // adminSessions / adminTickets / ownerUserId，手挑就会漏，漏了测的就不是生产
  // 实现而是一个残缺的拼装件。
  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    runtimeSpoolDatabase: spool,
    dashboardLog: [],
    config: {},
  });
  const bind = (name) => CyberbossApp.prototype[name].bind(app);
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "panel-token",
    firstRunProvider: () => firstRun,
    adminOverview: () => ({ ok: true, lines: [], users: 0, messagesToday: 0, log: [] }),
    adminConversations: () => ({ ok: true, threads: [], people: [] }),
    adminPersonaRead: () => ({ ok: true, persona: defaultPersona(), tones: [], lengths: [] }),
    adminPersonaWrite: (input) => ({ ok: true, persona: normalizePersona(input) }),
    adminSessionIssue: bind("issueAdminSession"),
    adminSessionVerify: bind("adminSessionValid"),
    adminSessionRevoke: bind("revokeAdminSession"),
    logger: { warn() {} },
  });
  const address = await server.start();
  t.after(() => server.stop());
  return { port: address.port, spool, app };
}

const loginWithToken = (port) => request(port, {
  method: "POST",
  requestPath: "/admin/api/login",
  headers: { "x-admin-token": "panel-token", "content-type": "application/json" },
  body: "{}",
});

// ── 会话 ────────────────────────────────────────────────────

test("用令牌登录一次，之后只靠 cookie 就能读对话和语气", async (t) => {
  const h = await loginServer(t);

  assert.equal(
    (await request(h.port, { requestPath: "/admin/api/conversations" })).status,
    401,
    "没登录时读不了",
  );

  const login = await loginWithToken(h.port);
  assert.equal(login.status, 200);
  assert.equal(login.json.ok, true);
  assert.ok(login.json.csrf, "写操作要用的 csrf 必须回给页面");

  const setCookie = String(login.headers["set-cookie"] || "");
  assert.match(setCookie, /HttpOnly/, "会话 cookie 必须 HttpOnly——页面脚本不该读得到它");
  assert.match(setCookie, /Secure/);
  assert.match(setCookie, /SameSite=Strict/, "SameSite=Strict 挡住跨站带 cookie 的写入");

  const cookie = { cookie: cookieOf(login) };
  for (const route of ["/admin/api/conversations", "/admin/api/persona", "/admin/api/overview"]) {
    const probe = await request(h.port, { requestPath: route, headers: cookie });
    assert.equal(probe.status, 200, `${route} 应当只凭 cookie 就能读`);
  }
});

test("退出之后那张 cookie 立刻作废", async (t) => {
  const h = await loginServer(t);
  const login = await loginWithToken(h.port);
  const cookie = { cookie: cookieOf(login) };
  assert.equal((await request(h.port, { requestPath: "/admin/api/conversations", headers: cookie })).status, 200);

  const out = await request(h.port, {
    method: "POST", requestPath: "/admin/api/logout", headers: cookie, body: "",
  });
  assert.equal(out.status, 200);
  assert.match(String(out.headers["set-cookie"] || ""), /Max-Age=0/, "浏览器那一份也要清掉");

  assert.equal(
    (await request(h.port, { requestPath: "/admin/api/conversations", headers: cookie })).status,
    401,
    "退出之后同一张 cookie 必须再也进不去",
  );
});

test("伪造或残缺的 cookie 一律进不去", async (t) => {
  const h = await loginServer(t);
  const forged = [
    "cb_session=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "cb_session=",
    "cb_session=%2e%2e%2fetc%2fpasswd",
    "unrelated=1",
  ];
  for (const value of forged) {
    const probe = await request(h.port, {
      requestPath: "/admin/api/conversations",
      headers: { cookie: value },
    });
    assert.equal(probe.status, 401, `${value} 必须被拒`);
  }
});

test("首次运行免令牌换不出会话——那条规则只对概览成立", async (t) => {
  // firstRun 时概览确实免令牌（库里还没有任何用户数据）。但登录接口要是也跟着
  // 免，任何人在主人绑定之前访问一次就拿到了一张长期通行证。
  const h = await loginServer(t, { firstRun: true });

  assert.equal(
    (await request(h.port, { requestPath: "/admin/api/overview" })).status,
    200,
    "概览的首次运行免令牌规则没有被改动",
  );

  const stolen = await request(h.port, {
    method: "POST",
    requestPath: "/admin/api/login",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(stolen.status, 401);
  assert.equal(stolen.headers["set-cookie"], undefined, "被拒的登录不得发出任何 cookie");
});

test("已经登录着可以续期，换到的是一张新 cookie，旧的作废", async (t) => {
  const h = await loginServer(t);
  const first = await loginWithToken(h.port);
  const firstCookie = cookieOf(first);

  const renewed = await request(h.port, {
    method: "POST",
    requestPath: "/admin/api/login",
    headers: { cookie: firstCookie, "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(renewed.status, 200, "带着有效 cookie 来续期必须成功");
  const secondCookie = cookieOf(renewed);
  assert.notEqual(secondCookie, firstCookie, "续期要换一张新的，不是原样返回");

  assert.equal(
    (await request(h.port, { requestPath: "/admin/api/conversations", headers: { cookie: secondCookie } })).status,
    200,
  );
  assert.equal(
    (await request(h.port, { requestPath: "/admin/api/conversations", headers: { cookie: firstCookie } })).status,
    401,
    "续期之后旧的那张必须立刻失效",
  );
});

// ── 一次性票 ────────────────────────────────────────────────

test("微信来的一次性票能换会话，且只能换一次", async (t) => {
  const h = await loginServer(t);
  const ticket = new SqliteAdminLoginTickets({ database: h.spool.database }).issue();

  const first = await request(h.port, {
    method: "POST",
    requestPath: "/admin/api/login",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticket: ticket.token }),
  });
  assert.equal(first.status, 200, "票换不到会话的话，微信那条链接就是废的");
  assert.match(String(first.headers["set-cookie"] || ""), /HttpOnly/);

  // 链接会一直留在聊天记录里，所以第二次必须失败。
  const second = await request(h.port, {
    method: "POST",
    requestPath: "/admin/api/login",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticket: ticket.token }),
  });
  assert.equal(second.status, 401);
  assert.equal(second.headers["set-cookie"], undefined);
});

test("票会过期", (t) => {
  const spool = openSpool(t, "cb-ticket-");
  let clock = 1_000_000;
  const tickets = new SqliteAdminLoginTickets({
    database: spool.database,
    now: () => clock,
    ttlMs: 5 * 60_000,
  });

  const fresh = tickets.issue();
  clock += 4 * 60_000;
  assert.ok(tickets.consume(fresh.token), "没过期时能用");

  const stale = tickets.issue();
  clock += 6 * 60_000;
  assert.throws(() => tickets.consume(stale.token), /TICKET_INVALID/, "过了 5 分钟必须作废");
});

test("乱编的票一律拒绝，用过的和不存在的回同一个错误码", (t) => {
  const spool = openSpool(t, "cb-ticket2-");
  const tickets = new SqliteAdminLoginTickets({ database: spool.database });

  for (const bad of ["", "短", "a".repeat(200), "有中文的票", null, 42, {}]) {
    assert.throws(() => tickets.consume(bad), /TICKET_INVALID/, `${String(bad)} 必须被拒`);
  }

  const used = tickets.issue();
  tickets.consume(used.token);
  // 不区分"没这张"和"用过了"：否则可以拿它来试探哪些票存在过。
  assert.throws(() => tickets.consume(used.token), /TICKET_INVALID/);
});

test("票只存哈希——库里被人看到也换不出可用的链接", (t) => {
  const spool = openSpool(t, "cb-ticket3-");
  const ticket = new SqliteAdminLoginTickets({ database: spool.database }).issue();
  const rows = spool.database.prepare("SELECT * FROM admin_login_tickets").all();

  assert.equal(rows.length, 1);
  assert.equal(
    JSON.stringify(rows).includes(ticket.token),
    false,
    "明文票一个字节都不许落库",
  );
});

// ── 微信入口 ────────────────────────────────────────────────

test("微信里说「后台」拿到的是一条一次性链接，不是那串长期令牌", (t) => {
  const app = bootApp(t);
  const link = app.issueAdminLoginLink();

  assert.match(link, /^https:\/\/boss\.example\.com\/admin#t=/, "票放在片段里：不进请求行，也就不进访问日志");
  assert.match(link, /只能用一次/);
  const adminToken = app.config.adminToken || "";
  if (adminToken) {
    assert.equal(link.includes(adminToken), false, "长期令牌一个字都不许出现在聊天记录里");
  }

  const token = link.split("#t=")[1].split("\n")[0];
  assert.equal(app.issueAdminSession({ ticket: token }).ok, true);
  assert.equal(app.issueAdminSession({ ticket: token }).ok, false, "同一条链接不能用第二次");
});

test("普通用户在 /setup 拿到的会话进不了后台", (t) => {
  const app = bootApp(t);
  const sessions = new SqliteSessionTokenService({
    database: app.runtimeSpoolDatabase.database,
  });

  // 造一个真的普通用户，再用同一张 web_sessions 表给他发一个会话——这正是
  // /setup 的做法。后台如果不校验身份，他就能读到所有人的聊天记录。
  const invite = app.userAdmission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
  app.userAdmission.admit({ botAccountRef: "bot", senderRef: "outsider", text: invite.code });
  app.userAdmission.admit({ botAccountRef: "bot", senderRef: "outsider", text: "同意并开始" });
  const decision = app.userAdmission.admit({ botAccountRef: "bot", senderRef: "outsider", text: "hi" });
  const theirs = sessions.issue({ userId: decision.userContext.userId });

  assert.equal(
    app.adminSessionValid(`cb_session=${theirs.token}`),
    false,
    "普通用户的会话在同一张表里，不校验身份就等于把后台开放给他",
  );

  const mine = app.issueAdminSession({});
  const mineToken = String(mine.setCookie).split("=")[1].split(";")[0];
  assert.equal(app.adminSessionValid(`cb_session=${mineToken}`), true, "主人自己的会话要通得过");
});

test("普通用户说「后台」只拿到普通帮助，不会拿到链接", (t) => {
  const app = bootApp(t);
  const invite = app.userAdmission.issueInvite({ maxUses: 1, ttlMs: 600_000 });
  app.userAdmission.admit({ botAccountRef: "bot", senderRef: "outsider", text: invite.code });
  app.userAdmission.admit({ botAccountRef: "bot", senderRef: "outsider", text: "同意并开始" });

  for (const word of ["后台", "面板", "网站", "控制台", "管理后台"]) {
    const decision = app.userAdmission.admit({
      botAccountRef: "bot", senderRef: "outsider", text: word,
    });
    assert.notEqual(decision.route, "admin_link", `普通用户说「${word}」不得走到后台链接`);
    assert.equal(decision.text?.includes("admin#t=") || false, false, "回复里不许出现后台链接");
  }
});
