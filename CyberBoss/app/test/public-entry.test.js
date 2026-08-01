"use strict";

// 公开入口：陌生人扫码进来的那条路。
//
// 用户原话：「不需要邀请码 二维码扫码后默认连接使用」。
//
// 开放模式把门打开了，于是挡住"任何扫到码的人都来烧主人额度"的就只剩席位上限
// 这一个东西——R19 AC-039 本来就要求第六个人在**任何模型调用之前**被拒，而那条
// 在真实链路上一直没实现（ordinary_user_seats 所在的迁移根本没被应用）。所以
// 这一套测试的重心有两个：门确实开了，以及门口确实有人数着。
//
// 另一半是公开页本身：它必须任何人都能打开（那是它存在的意义），也必须一个字
// 的运营信息都不吐——人数、用量、状态都不行。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { UserAdmissionService } = require("../src/core/user-admission");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { PortalHttpServer } = require("../src/services/portal/portal-server");
const {
  MAX_SEATS,
  PersonaStore,
  normalizeAccess,
  normalizeEntryUrl,
} = require("../src/services/persona/persona-store");

const ENCRYPTION_KEY = Buffer.alloc(32, 71);
const IDENTITY_KEY = Buffer.alloc(32, 73);
const BOT = "bot-public";

function openSpool(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-public-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  return spool;
}

function admission(spool, { mode = "open", seats = 5 } = {}) {
  return new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-sender"],
    registrationMode: mode,
    seatLimitProvider: () => seats,
  });
}

// 开放模式下，说一句话就开通了——不需要邀请码，也不需要再回一句「同意并开始」。
// 告知照发，但不挡路（CB_REQUIRE_EXPLICIT_CONSENT=true 可退回两步式）。
function activate(service, senderRef) {
  return service.admit({ botAccountRef: BOT, senderRef, text: "你好" });
}

// ── 入口地址校验 ────────────────────────────────────────────

test("入口地址只收 https 和 weixin，别的一律清空", () => {
  assert.equal(normalizeEntryUrl("https://weixin.qq.com/x/abc"), "https://weixin.qq.com/x/abc");
  assert.equal(normalizeEntryUrl("weixin://dl/chat?x=1"), "weixin://dl/chat?x=1");
  // 这几个挂到公开页的二维码上，就是把攻击面直接发给别人扫。
  for (const bad of [
    "javascript:alert(1)",
    "data:text/html,<script>x</script>",
    "http://a.com",
    "https://user:pass@a.com",
    "not a url",
    "https://a.com/\nSet-Cookie: x=1",
    "",
    null,
  ]) {
    assert.equal(normalizeEntryUrl(bad), "", `${String(bad)} 必须被清掉`);
  }
});

test("席位数被夹在 0 和上限之间，乱填退回默认", () => {
  assert.equal(normalizeAccess({ seats: 999 }).seats, MAX_SEATS);
  assert.equal(normalizeAccess({ seats: -3 }).seats, 0);
  assert.equal(normalizeAccess({ seats: "三" }).seats, 5);
  // 模式分三态（CB9-300 / AC-045）：
  //   设了但认不出来 → invite。访问控制字段，看不懂的值一律往关着的那边靠。
  //   明确设了 → 就是它。
  //   **没设过 → null**，不是 invite：全新安装的主人从没选过关闭公开注册，
  //     不能替他选。null 让 resolveRegistrationMode 往下走到环境变量和产品
  //     默认（open）——公开页存在的意义就是让人不用找主人要邀请码。
  assert.equal(normalizeAccess({ mode: "OPEN" }).mode, "invite");
  assert.equal(normalizeAccess({ mode: "open" }).mode, "open");
  assert.equal(normalizeAccess({ mode: "invite" }).mode, "invite");
  assert.equal(normalizeAccess({}).mode, null);
});

// ── 开放模式 ────────────────────────────────────────────────

test("开放模式下扫码就能用：第一句话就是正式对话，不用先回「同意并开始」", (t) => {
  const service = admission(openSpool(t), { mode: "open" });

  // 第一句话就被当成正式对话。以前这里要三步（说句话 -> 同意 -> 再说一句），
  // 而那三步里没有一步是他想做的事——他只是想问个问题。
  const first = service.admit({ botAccountRef: BOT, senderRef: "stranger", text: "你好" });
  assert.equal(first.route, "user", "开放模式下第一句话就该走普通用户那条路");
  assert.equal(/邀请码/.test(first.text || ""), false, "开放模式下不该再提邀请码");
  assert.equal(/同意并开始/.test(first.text || ""), false, "不该再要他回一句同意");

  // 「不同意」仍然是一条随时可走的出口。
  const declined = service.admit({ botAccountRef: BOT, senderRef: "other", text: "不同意" });
  assert.equal(declined.route, "reply");
  assert.match(declined.text, /已停止开通/);
});

test("邀请模式仍然要码——开放只是一个可以关掉的开关", (t) => {
  const service = admission(openSpool(t), { mode: "invite" });
  const first = service.admit({ botAccountRef: BOT, senderRef: "stranger", text: "你好" });
  assert.match(first.text, /邀请码/);
  assert.notEqual(first.route, "user");
});

// ── 席位闸门 ────────────────────────────────────────────────

test("名额不是一道门：第 N+1 个人照样能进，只是要自己填密钥", (t) => {
  // 之前我把它做成了"第六个人直接被拒"，那是错的。主人的原话是
  // 「前面五个人都用我的额度，第六个人开始就需要用 ai 密钥」——名额限的是
  // 谁花主人的钱，不是谁能不能用。
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 2 });

  activate(service, "user-1");
  activate(service, "user-2");
  const third = activate(service, "user-3");

  assert.equal(third.route, "user", "第三个人也要能开通，只是额度来源不同");
  assert.equal(service.users.countActiveOrdinaryUsers(), 3);
});

test("排队按开通先后，先来的占主人的额度", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 2 });

  const a = activate(service, "early-1").userContext.userId;
  const b = activate(service, "early-2").userContext.userId;
  const c = activate(service, "late-3").userContext.userId;

  assert.equal(service.users.ordinaryUserRank(a), 1);
  assert.equal(service.users.ordinaryUserRank(b), 2);
  assert.equal(service.users.ordinaryUserRank(c), 3);
  // 主人不在这个名单里。
  assert.equal(service.users.ordinaryUserRank(spool.ownerUserId), 0);
});

test("前 N 个用主人的密钥，第 N+1 个开始拿不到", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 2 });
  const ids = ["u1", "u2", "u3"].map((who) => activate(service, who).userContext.userId);

  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    userAdmission: service,
    personaStore: { read: () => ({ access: { seats: 2 } }) },
    config: {},
    // 假装主人配了一把密钥。真实实现从 systemd credential 读，这里只测分配规则。
    ownerCredentialCache: Object.freeze({ providerId: "deepseek", model: "deepseek-chat", apiKey: "sk-owner" }),
  });

  assert.ok(app.resolveOwnerQuotaFor(ids[0]), "第 1 个应当能用主人的额度");
  assert.ok(app.resolveOwnerQuotaFor(ids[1]), "第 2 个也能");
  assert.equal(app.resolveOwnerQuotaFor(ids[2]), null, "第 3 个必须自己填密钥");
  // 主人自己不走这条路。
  assert.equal(app.resolveOwnerQuotaFor(spool.ownerUserId), null);
});

test("主人自己没配密钥时，谁都拿不到兜底", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 5 });
  const id = activate(service, "u1").userContext.userId;

  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    userAdmission: service,
    personaStore: { read: () => ({ access: { seats: 5 } }) },
    config: {},
    ownerCredentialCache: null,
  });
  // 没有密钥就是没有。宁可让人自己填，也不能拿一个不存在的东西去调模型。
  assert.equal(app.resolveOwnerQuotaFor(id), null);
});

test("名额设成 0 时谁都不用主人的额度", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 0 });
  const id = activate(service, "u1").userContext.userId;

  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    userAdmission: service,
    personaStore: { read: () => ({ access: { seats: 0 } }) },
    config: {},
    ownerCredentialCache: Object.freeze({ providerId: "deepseek", model: "deepseek-chat", apiKey: "sk-owner" }),
  });
  assert.equal(app.resolveOwnerQuotaFor(id), null);
});

test("主人不占名额", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 1 });

  const owner = service.admit({ botAccountRef: BOT, senderRef: "owner-sender", text: "在吗" });
  assert.equal(owner.route, "owner");
  // 唯一那个免费名额应当留给普通用户，主人不算在里面。
  assert.equal(activate(service, "guest").route, "user");
  assert.equal(service.users.countActiveOrdinaryUsers(), 1);
});

test("改小名额不影响已经开通的人能不能说话", (t) => {
  const spool = openSpool(t);
  let seats = 3;
  const service = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-sender"],
    registrationMode: "open",
    seatLimitProvider: () => seats,
  });
  activate(service, "old-timer");

  // 主人事后把名额调小到 0：已经在用的人不该被踢出去，只是不再进新人。
  seats = 0;
  assert.equal(
    service.admit({ botAccountRef: BOT, senderRef: "old-timer", text: "在吗" }).route,
    "user",
    "改小名额不该把已经在用的人挡在外面",
  );
  // 新人照样能开通——名额限的是花谁的钱，不是能不能用。
  assert.equal(activate(service, "newcomer").route, "user");
});

test("名额读不出来时照常放人进来", (t) => {
  const spool = openSpool(t);
  const service = new UserAdmissionService({
    database: spool.database,
    identityKey: IDENTITY_KEY,
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["owner-sender"],
    registrationMode: "open",
    seatLimitProvider: () => { throw new Error("设置读坏了"); },
  });
  // 判定坏掉时"开放模式"变成"谁都进不来"是最糟的失败方式：主人看不出原因，
  // 别人只觉得这东西坏了。
  assert.equal(activate(service, "somebody").route, "user");
});

// ── 公开页 ──────────────────────────────────────────────────

function request(port, requestPath) {
  return new Promise((resolve, reject) => {
    const call = http.request({ host: "127.0.0.1", port, method: "GET", path: requestPath }, (response) => {
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
        resolve({ status: response.statusCode, text, json });
      });
    });
    call.on("error", reject);
    call.end();
  });
}

async function publicServer(t, entry) {
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "tok",
    firstRunProvider: () => false,
    publicEntry: () => entry,
    logger: { warn() {} },
  });
  const address = await server.start();
  t.after(() => server.stop());
  return address.port;
}

test("公开页和它的接口不要任何凭据——那正是它存在的意义", async (t) => {
  const port = await publicServer(t, {
    ok: true, ready: true, status: "ready",
    qrDataUri: "data:image/svg+xml;base64,AAA=", open: true, full: false,
    message: "用微信扫这个码加它，然后随便说句话就能用。",
  });

  const page = await request(port, "/join");
  assert.equal(page.status, 200);
  assert.match(page.text, /加我聊天/);
  assert.equal(page.text.includes("__CSP_NONCE__"), false, "占位符必须已经替换掉");

  const api = await request(port, "/api/join");
  assert.equal(api.status, 200);
  assert.equal(api.json.ready, true);
  assert.match(api.json.qrDataUri, /^data:image\//);
});

test("公开接口不吐任何运营信息", async (t) => {
  const port = await publicServer(t, {
    ok: true, ready: true, status: "ready",
    qrDataUri: "data:image/svg+xml;base64,AAA=", open: true, full: false,
    message: "用微信扫这个码加它，然后随便说句话就能用。",
  });
  const api = await request(port, "/api/join");

  // 只允许这几个键。多一个就可能是把人数、用量、内部状态漏出去了。
  assert.deepEqual(
    Object.keys(api.json).sort(),
    ["full", "message", "ok", "open", "qrDataUri", "ready", "status"],
  );
  for (const leak of ["seats", "users", "count", "token", "usage", "quota"]) {
    assert.equal(api.text.includes(leak), false, `公开接口不该出现 ${leak}`);
  }
});

test("入口没配好时公开页说人话，不露任何东西", async (t) => {
  const port = await publicServer(t, {
    ok: true, ready: false, status: "pending_entry_qr", message: "入口二维码还没配好，请稍后再来。",
  });
  const api = await request(port, "/api/join");
  assert.equal(api.json.ready, false);
  assert.equal(api.json.qrDataUri, undefined);
  assert.match(api.json.message, /还没配好/);
});

test("公开入口出错时也只说「还没准备好」，不吐内部错误码", async (t) => {
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "tok",
    firstRunProvider: () => false,
    publicEntry: () => { throw new Error("SOMETHING_INTERNAL"); },
    logger: { warn() {} },
  });
  const address = await server.start();
  t.after(() => server.stop());

  const api = await request(address.port, "/api/join");
  assert.equal(api.status, 200);
  assert.equal(api.json.ready, false);
  assert.equal(api.text.includes("SOMETHING_INTERNAL"), false);
});

// ── 设置落库 ────────────────────────────────────────────────

test("开放模式、席位、入口地址都存得住读得回", (t) => {
  const spool = openSpool(t);
  const store = new PersonaStore({ database: spool });
  store.write({
    access: { mode: "open", seats: 3, entryUrl: "https://weixin.qq.com/x/abc" },
  });

  const reread = new PersonaStore({ database: spool }).read().access;
  assert.equal(reread.mode, "open");
  assert.equal(reread.seats, 3);
  assert.equal(reread.entryUrl, "https://weixin.qq.com/x/abc");
});

test("存进去的非法入口地址会被清空，而不是原样留着", (t) => {
  const spool = openSpool(t);
  const store = new PersonaStore({ database: spool });
  store.write({ access: { mode: "open", entryUrl: "javascript:alert(1)" } });
  assert.equal(store.read().access.entryUrl, "", "非法地址一个字节都不该落库");
});

test("app 把面板上的模式和席位真的接给了 UserAdmission", () => {
  // 接线断了的话，面板上改成开放模式、界面显示得好好的，实际还是要邀请码。
  const source = fs.readFileSync(
    path.join(__dirname, "..", "src", "core", "app.js"),
    "utf8",
  );
  assert.match(source, /registrationMode:\s*this\.resolveRegistrationMode\(\)/);
  assert.match(source, /seatLimitProvider:\s*\(\)\s*=>\s*this\.resolveSeatLimit\(\)/);
  assert.match(source, /publicEntry:\s*\(\)\s*=>\s*this\.buildPublicEntry\(\)/);
});

test("面板设置优先于环境变量，读不出来才退回配置", (t) => {
  const spool = openSpool(t);
  const app = Object.assign(Object.create(CyberbossApp.prototype), {
    runtimeSpoolDatabase: spool,
    personaStore: new PersonaStore({ database: spool }),
    config: { registrationMode: "invite" },
  });

  assert.equal(app.resolveRegistrationMode(), "invite", "没设过就跟着配置走");
  app.personaStore.write({ access: { mode: "open", seats: 7 } });
  assert.equal(app.resolveRegistrationMode(), "open", "面板改了就得听面板的");
  assert.equal(app.resolveSeatLimit(), 7);

  // 存储读不出来时：模式退回配置，席位不设限。
  const broken = Object.assign(Object.create(CyberbossApp.prototype), {
    personaStore: { read() { throw new Error("坏了"); } },
    config: { registrationMode: "invite" },
  });
  assert.equal(broken.resolveRegistrationMode(), "invite");
  assert.equal(broken.resolveSeatLimit(), null);
});
