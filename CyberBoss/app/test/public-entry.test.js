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

// 走完整的开通流程：说句话 -> 同意 -> 再说一句。开放模式下不需要邀请码。
// 第三步是必要的：同意那一轮回的是「已开通」这条 reply，真正以普通用户身份
// 被路由要等下一句话。
function activate(service, senderRef) {
  service.admit({ botAccountRef: BOT, senderRef, text: "你好" });
  service.admit({ botAccountRef: BOT, senderRef, text: "同意并开始" });
  return service.admit({ botAccountRef: BOT, senderRef, text: "在吗" });
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
  // 模式只认 open 这一个字，别的都算 invite——默认必须是关着的那一边。
  assert.equal(normalizeAccess({ mode: "OPEN" }).mode, "invite");
  assert.equal(normalizeAccess({ mode: "open" }).mode, "open");
  assert.equal(normalizeAccess({}).mode, "invite");
});

// ── 开放模式 ────────────────────────────────────────────────

test("开放模式下不需要邀请码，说句话再同意就能用", (t) => {
  const service = admission(openSpool(t), { mode: "open" });

  const first = service.admit({ botAccountRef: BOT, senderRef: "stranger", text: "你好" });
  assert.notEqual(first.route, "user", "还没同意就不算开通");
  assert.equal(first.modelCalls, 0, "开通流程一次模型调用都不能花");
  assert.match(first.text, /同意并开始/, "第一句话就要告诉他下一步怎么做");
  assert.equal(/邀请码/.test(first.text), false, "开放模式下不该再提邀请码");

  const active = service.admit({ botAccountRef: BOT, senderRef: "stranger", text: "同意并开始" });
  assert.match(active.text, /已开通/);
  assert.equal(
    service.admit({ botAccountRef: BOT, senderRef: "stranger", text: "在吗" }).route,
    "user",
  );
});

test("邀请模式仍然要码——开放只是一个可以关掉的开关", (t) => {
  const service = admission(openSpool(t), { mode: "invite" });
  const first = service.admit({ botAccountRef: BOT, senderRef: "stranger", text: "你好" });
  assert.match(first.text, /邀请码/);
  assert.notEqual(first.route, "user");
});

// ── 席位闸门 ────────────────────────────────────────────────

test("席位满了之后第 N+1 个人被拒，且一行用户都不建", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 2 });

  activate(service, "user-1");
  activate(service, "user-2");
  assert.equal(service.users.countActiveOrdinaryUsers(), 2);

  const denied = service.admit({ botAccountRef: BOT, senderRef: "user-3", text: "你好" });
  assert.match(denied.text, /名额.*满/, "要说人话，不能吐错误码");
  assert.equal(denied.modelCalls, 0, "被拒的人不得花掉任何模型调用");
  assert.equal(
    service.users.countActiveOrdinaryUsers(),
    2,
    "被拒时连 pending 的用户行都不该建——建了等于既占位子又开通不了",
  );

  // 再说几句也还是进不来，不会因为反复尝试就漏进去。
  for (const text of ["同意并开始", "你好", "在吗"]) {
    const again = service.admit({ botAccountRef: BOT, senderRef: "user-3", text });
    assert.notEqual(again.route, "user", `「${text}」不该让满员的门开一条缝`);
  }
});

test("主人不占席位", (t) => {
  const spool = openSpool(t);
  const service = admission(spool, { mode: "open", seats: 1 });

  // 主人先说话。
  const owner = service.admit({ botAccountRef: BOT, senderRef: "owner-sender", text: "在吗" });
  assert.equal(owner.route, "owner");
  // 席位仍然是满的可用状态：主人不算在里面。
  const guest = activate(service, "guest");
  assert.equal(guest.route, "user", "唯一的那个席位应当留给普通用户");
  assert.equal(service.users.countActiveOrdinaryUsers(), 1);
});

test("已经开通的人不会被席位闸门挡住", (t) => {
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
  assert.notEqual(
    service.admit({ botAccountRef: BOT, senderRef: "newcomer", text: "你好" }).route,
    "user",
  );
});

test("席位读不出来时不设限，而不是把所有人挡住", (t) => {
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
