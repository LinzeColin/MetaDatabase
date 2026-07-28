"use strict";

// 主人后台的三件事：不再自动回执、语气可控、每一条来信和每一条回复都看得到。
//
// 这一套刻意走真实构造路径——bootstrap → readConfig → new CyberbossApp →
// initializeDurableInbox，和 `cyberboss start` 做的事一样。本仓已经五次出现
// 「测试全绿但那段代码在真实链路上从未被执行」，所以"回执没了"这件事必须由
// 真正被构造出来的那个 DurableInboxCoordinator 来证明，不能由一段单独 new 出来
// 的协调器来证明——后者证明的是协调器支持关掉回执，不是这台机器关掉了回执。

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { assembleRuntimeTurnText } = require("../src/core/inbound-turn");
const { bootstrapInstallation } = require("../src/core/bootstrap");
const { readConfig } = require("../src/core/config");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { PortalHttpServer } = require("../src/services/portal/portal-server");
const {
  PersonaStore,
  TONE_PRESETS,
  defaultPersona,
  normalizePersona,
  renderPersonaInstruction,
} = require("../src/services/persona/persona-store");

const ENCRYPTION_KEY = Buffer.alloc(32, 23);
const IDENTITY_KEY = Buffer.alloc(32, 29);

function tempHome(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-panel-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

// 和 first-run-experience 里的同名函数一样：真的走一遍安装与配置读取，
// 拿到一个真的 app 实例。
function bootApp(t) {
  const home = tempHome(t);
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
  set("CB_DURABLE_OUTBOX", "true");
  set("CB_MULTI_USER", "true");
  set("CB_REGISTRATION_MODE", "invite");
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

// ── 一、不再自动回执 ─────────────────────────────────────

test("真实构造出来的 durable inbox 不再挂自动回执", (t) => {
  const app = bootApp(t);

  assert.ok(app.durableInboxCoordinator, "durable inbox 必须真的建起来了，否则这条测试什么都没证明");
  assert.ok(app.outboxWorker, "outbox 也必须建起来——回执之所以曾经存在，正是因为它在");
  // 关键那一条：outbox 在、协调器在，但收下消息时不再有任何回调去 stage 消息。
  assert.equal(
    app.durableInboxCoordinator.onAccepted,
    null,
    "收下消息不得再自动回一句「收到，正在处理」——那句话让它一点也不像人",
  );
});

test("整个 src 里不再有任何地方 stage accepted 回执", () => {
  // onAccepted 是当时那句话的挂点，但删掉挂点不等于删掉行为——换个地方 stage
  // 一条 messageKind:"accepted" 同样会让用户再看到那句话。这条扫的是行为本身。
  const root = path.join(__dirname, "..", "src");
  const offenders = [];
  const walk = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!entry.name.endsWith(".js")) {
        continue;
      }
      const source = fs.readFileSync(full, "utf8");
      if (/messageKind:\s*["']accepted["']/.test(source)) {
        offenders.push(path.relative(root, full));
      }
    }
  };
  walk(root);
  assert.deepEqual(offenders, [], "不允许再有任何代码路径 stage accepted 回执");
});

// ── 二、语气 ─────────────────────────────────────────────

test("语气设置归一化：非法值退回默认，自定义内容按上限截断", () => {
  const fallback = normalizePersona({ tone: "不存在的语气", length: "超长", emoji: "yes" });
  assert.equal(fallback.tone, defaultPersona().tone);
  assert.equal(fallback.length, defaultPersona().length);
  assert.equal(fallback.emoji, false, "emoji 只认真正的 true，字符串不算");

  const long = normalizePersona({ note: "字".repeat(900), callMe: "名".repeat(90) });
  assert.equal(long.note.length, 500);
  assert.equal(long.callMe.length, 24);

  // 控制字符会把拼出来的提示词结构搞乱，必须先去掉；换行是正常输入，要留下。
  const dirty = normalizePersona({ note: "第一行\u0000\u001b[31m\n第二行" });
  assert.equal(dirty.note.includes("\u0000"), false);
  assert.equal(dirty.note.includes("\u001b"), false);
  assert.equal(dirty.note.includes("\n第二行"), true);
});

test("语气存储真的落库并读得回来", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-persona-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());

  const store = new PersonaStore({ database: spool });
  assert.equal(store.read().tone, defaultPersona().tone, "没设过就是默认值");

  store.write({ tone: "quiet", length: "short", emoji: true, callMe: "老板", note: "别问我今天过得怎么样" });

  // 换一个实例再读：证明它落的是数据库，不是内存里的一个字段。
  const reread = new PersonaStore({ database: spool }).read();
  assert.equal(reread.tone, "quiet");
  assert.equal(reread.length, "short");
  assert.equal(reread.emoji, true);
  assert.equal(reread.callMe, "老板");
  assert.equal(reread.note, "别问我今天过得怎么样");
  assert.ok(reread.updatedAt, "必须记下改动时间");
});

test("语气块贴在这一轮消息的最前面，且基线永远在", () => {
  const instruction = renderPersonaInstruction({ tone: "plain", length: "short", emoji: false });
  const text = assembleRuntimeTurnText({
    prepared: {
      originalText: "帮我看看这个",
      receivedAt: "2026-07-28T09:00:00.000Z",
      attachments: [],
    },
    personaInstruction: instruction,
  });

  assert.ok(text.startsWith("[怎么说话]"), "语气块必须在最前面，否则会被后面的附件段落挤远");
  assert.ok(text.includes("帮我看看这个"), "用户的原话不能被语气块顶掉");
  assert.ok(text.indexOf("[怎么说话]") < text.indexOf("帮我看看这个"));
  // 基线里那条正是这次改动的起因：不许再说"收到/正在处理"。
  assert.match(instruction, /不要说「收到」/);
  assert.match(instruction, /不要自称 AI/);
  assert.match(instruction, /有话直说/, "选中的语气必须真的进到指令里");
});

test("不给语气时，组装出来的文本和从前一模一样", () => {
  const prepared = {
    originalText: "在吗",
    receivedAt: "2026-07-28T09:00:00.000Z",
    attachments: [],
  };
  const withoutPersona = assembleRuntimeTurnText({ prepared });
  assert.equal(withoutPersona.startsWith("[怎么说话]"), false);
  assert.ok(withoutPersona.includes("在吗"));
});

test("语气在真实链路上可达：app 自己就能渲染出当前语气块", (t) => {
  const app = bootApp(t);

  assert.ok(app.personaStore, "personaStore 必须在构造时就建好");
  const before = app.currentPersonaInstruction();
  assert.match(before, /\[怎么说话\]/);

  app.writeDashboardPersona({ tone: "quiet", length: "short", emoji: false, note: "夜里说话轻一点" });
  const after = app.currentPersonaInstruction();
  assert.match(after, /话少、克制/, "改完之后，下一轮读到的必须是新语气");
  assert.match(after, /夜里说话轻一点/);

  // buildRuntimeTurn 是真实链路上唯一的组装点，它必须真的把这段带上。
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "core", "app.js"), "utf8");
  assert.match(
    source,
    /personaInstruction:\s*this\.currentPersonaInstruction\(\)/,
    "buildRuntimeTurn 必须把语气传进 assembleRuntimeTurnText，否则面板改了也没用",
  );
});

test("后台读语气时把真正发给模型的原话也给出来", (t) => {
  const app = bootApp(t);
  const view = app.readDashboardPersona();

  assert.equal(view.ok, true);
  assert.equal(view.tones.length, TONE_PRESETS.length);
  assert.ok(view.tones.every((tone) => tone.id && tone.label));
  assert.equal(view.preview, app.currentPersonaInstruction(), "预览必须是真话，不能是另写一份");
});

// ── 三、对话：来信与回复 ─────────────────────────────────

// acceptInbound 自己就建了 job，所以这里不用再建一遍——用的是生产类的真实
// 写入路径，不是手写 INSERT。
function seedTurn(spool, { senderId, text, replyText, replyStatus = "confirmed" }) {
  const accepted = spool.acceptInbound({
    source: "weixin",
    sourceAccountRef: "bot-panel",
    sourceMessageId: `msg-${senderId}-${text}`,
    userRef: senderId,
    messageType: "text",
    payload: { provider: "weixin", senderId, text },
    contextToken: `ctx-${senderId}`,
    workspaceAlias: "cyberboss",
    runtime: "codex",
    operationClass: "bounded_mutation",
  });
  if (replyText === undefined) {
    return { accepted };
  }
  const staged = spool.enqueueOutbox({
    jobId: accepted.jobId,
    dedupeKey: `dk${accepted.jobId}`,
    messageKind: "result",
    targetRef: { userId: senderId, contextToken: `ctx-${senderId}` },
    payload: replyText,
    maxAttempts: 5,
  });
  if (replyStatus === "pending") {
    return { accepted, staged };
  }
  // 走生产的领取→开始投递→确认/终止这条真实状态机，而不是手写 UPDATE：
  // 这些表上有约束和触发器，绕过去写出来的行在真实系统里不会出现。
  const owner = "panel-test-worker";
  spool.claimNextOutbox({ ownerId: owner });
  spool.markOutboxDispatchStarted(staged.id, { ownerId: owner });
  if (replyStatus === "confirmed") {
    spool.markOutboxConfirmed(staged.id, {
      ownerId: owner,
      providerConfirmation: {
        confirmed: true,
        clientId: spool.getOutbox(staged.id).provider_client_id,
        receiptHash: crypto.createHash("sha256").update(staged.id).digest("hex"),
      },
    });
  } else {
    spool.markOutboxTerminal(staged.id, { ownerId: owner, errorClass: "channel_rejected" });
  }
  return { accepted, staged };
}

function panelSpool(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-feed-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: ENCRYPTION_KEY,
    identityKey: IDENTITY_KEY,
  });
  t.after(() => spool.close());
  return spool;
}

test("对话一栏把来信和它的回复按 correlation 配上对，内容是解密后的真话", (t) => {
  const spool = panelSpool(t);
  seedTurn(spool, { senderId: "wx-a", text: "今天有点累", replyText: "那就早点睡。" });

  const app = { runtimeSpoolDatabase: spool, directReplyLog: [] };
  const feed = CyberbossApp.prototype.buildConversationFeed.call(app, {});

  assert.equal(feed.ok, true);
  assert.equal(feed.threads.length, 1);
  const thread = feed.threads[0];
  assert.equal(thread.who, "wx-a");
  assert.equal(thread.text, "今天有点累", "来信必须解密出原文，否则这一栏没有用");
  assert.equal(thread.available, true);
  assert.equal(thread.replies.length, 1);
  assert.equal(thread.replies[0].text, "那就早点睡。");
  assert.equal(thread.replies[0].delivered, true);
  assert.equal(thread.state.label, "已回复");
  assert.equal(thread.state.stuck, false);
  assert.equal(feed.unanswered, 0);
});

test("发不出去的回复必须显示成没答上，不能显示成已回复", (t) => {
  const spool = panelSpool(t);
  seedTurn(spool, {
    senderId: "wx-b",
    text: "帮我订个闹钟",
    replyText: "好，明早七点。",
    replyStatus: "failed_terminal",
  });

  const app = { runtimeSpoolDatabase: spool, directReplyLog: [] };
  const feed = CyberbossApp.prototype.buildConversationFeed.call(app, {});
  const thread = feed.threads[0];

  assert.equal(thread.replies[0].delivered, false);
  assert.equal(thread.replies[0].state, "发送失败，已放弃");
  assert.equal(thread.state.stuck, true, "去掉自动回执之后，「没答上」只能在这里看出来");
  assert.equal(feed.unanswered, 1);
});

test("完全没有回复的来信显示成还在处理，不会假装成功", (t) => {
  const spool = panelSpool(t);
  seedTurn(spool, { senderId: "wx-c", text: "在吗" });

  const app = { runtimeSpoolDatabase: spool, directReplyLog: [] };
  const thread = CyberbossApp.prototype.buildConversationFeed.call(app, {}).threads[0];

  assert.equal(thread.replies.length, 0);
  assert.equal(thread.state.label, "正在处理");
});

test("走 admission 直接回掉的那些消息也进对话栏，并标明重启后不保留", (t) => {
  const spool = panelSpool(t);
  seedTurn(spool, { senderId: "wx-d", text: "开始" });

  const app = { runtimeSpoolDatabase: spool, directReplyLog: [] };
  // 真实路径上这一句由 sendAdmissionReply 记下；这里直接调它记的那个方法。
  CyberbossApp.prototype.noteDirectReply.call(app, "wx-d", "把邀请码发给我就能开通。");

  const thread = CyberbossApp.prototype.buildConversationFeed.call(app, {}).threads[0];
  assert.equal(thread.replies.length, 1);
  assert.equal(thread.replies[0].text, "把邀请码发给我就能开通。");
  assert.match(thread.replies[0].source, /重启后不保留/, "内存里的东西必须说清楚是内存里的");
});

test("同一个人的多条来信不会把同一条直接回复重复挂上去", (t) => {
  const spool = panelSpool(t);
  seedTurn(spool, { senderId: "wx-e", text: "第一句" });
  seedTurn(spool, { senderId: "wx-e", text: "第二句" });

  const app = { runtimeSpoolDatabase: spool, directReplyLog: [] };
  CyberbossApp.prototype.noteDirectReply.call(app, "wx-e", "只回了一次");

  const threads = CyberbossApp.prototype.buildConversationFeed.call(app, {}).threads;
  const total = threads.reduce((sum, thread) => sum + thread.replies.length, 0);
  assert.equal(total, 1, "一条回复只能挂在一个地方，重复计数会让人以为它回了两次");
});

// ── 四、鉴权：这两条路永远要令牌 ─────────────────────────

function raw(port, { method = "GET", requestPath = "/", headers = {}, body = null } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === null ? null : Buffer.from(body);
    const request = http.request(
      {
        host: "127.0.0.1",
        port,
        method,
        path: requestPath,
        headers: { ...headers, ...(payload ? { "content-length": String(payload.length) } : {}) },
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
          resolve({ status: response.statusCode, text, json });
        });
      },
    );
    request.on("error", reject);
    if (payload) request.write(payload);
    request.end();
  });
}

async function panelServer(t, { firstRun }) {
  let written = null;
  const server = new PortalHttpServer({
    portal: { handle: () => ({ ok: true }) },
    port: 0,
    adminToken: "panel-token",
    firstRunProvider: () => firstRun,
    adminOverview: () => ({ ok: true, lines: [], users: 0, messagesToday: 0, log: [] }),
    adminConversations: (limit) => ({ ok: true, threads: [], limit }),
    adminPersonaRead: () => ({ ok: true, persona: defaultPersona(), tones: [], lengths: [] }),
    adminPersonaWrite: (input) => {
      written = input;
      return { ok: true, persona: normalizePersona(input) };
    },
    logger: { warn() {} },
  });
  const address = await server.start();
  t.after(() => server.stop());
  return { port: address.port, read: () => written };
}

test("首次运行免令牌只对概览成立；对话和语气在任何时候都要令牌", async (t) => {
  // firstRun=true 是免令牌那条规则最宽松的时候。概览此时确实免令牌——库里还
  // 没有任何用户数据。但对话读的是解密后的真实聊天，语气改的是每个人都会收到
  // 的说话方式，这两件事在这一刻同样必须先证明你是管理者。
  const h = await panelServer(t, { firstRun: true });

  const overview = await raw(h.port, { requestPath: "/admin/api/overview" });
  assert.equal(overview.status, 200, "概览在首次运行时免令牌，这条规则没有被改动");

  const talk = await raw(h.port, { requestPath: "/admin/api/conversations" });
  assert.equal(talk.status, 401);
  assert.equal(talk.json.code, "ADMIN_TOKEN_INVALID");
  assert.equal(talk.text.includes("threads"), false, "拒绝时一个字节的聊天内容都不能漏出去");

  const persona = await raw(h.port, { requestPath: "/admin/api/persona" });
  assert.equal(persona.status, 401);

  const write = await raw(h.port, {
    method: "POST",
    requestPath: "/admin/api/persona",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tone: "quiet" }),
  });
  assert.equal(write.status, 401);
  assert.equal(h.read(), null, "被拒的写不得落到任何地方");
});

test("带对令牌就能读对话、读写语气", async (t) => {
  const h = await panelServer(t, { firstRun: false });
  const authed = { "x-admin-token": "panel-token" };

  const talk = await raw(h.port, { requestPath: "/admin/api/conversations?limit=7", headers: authed });
  assert.equal(talk.status, 200);
  assert.equal(talk.json.ok, true);
  assert.equal(talk.json.limit, 7, "limit 必须真的传下去");

  const read = await raw(h.port, { requestPath: "/admin/api/persona", headers: authed });
  assert.equal(read.status, 200);
  assert.equal(read.json.ok, true);

  const write = await raw(h.port, {
    method: "POST",
    requestPath: "/admin/api/persona",
    headers: { ...authed, "content-type": "application/json" },
    body: JSON.stringify({ tone: "quiet", length: "short", emoji: true, note: "夜里轻一点" }),
  });
  assert.equal(write.status, 200);
  assert.equal(write.json.persona.tone, "quiet");
  assert.equal(h.read().note, "夜里轻一点");
});

test("令牌错一个字节也进不去", async (t) => {
  const h = await panelServer(t, { firstRun: false });

  const wrong = await raw(h.port, {
    requestPath: "/admin/api/conversations",
    headers: { "x-admin-token": "panel-tokem" },
  });
  assert.equal(wrong.status, 401);

  const shorter = await raw(h.port, {
    requestPath: "/admin/api/conversations",
    headers: { "x-admin-token": "panel" },
  });
  assert.equal(shorter.status, 401);
});

test("语气 body 不是 JSON 时明确回错，而不是当成空设置存进去", async (t) => {
  const h = await panelServer(t, { firstRun: false });

  const broken = await raw(h.port, {
    method: "POST",
    requestPath: "/admin/api/persona",
    headers: { "x-admin-token": "panel-token", "content-type": "application/json" },
    body: "{不是 JSON",
  });
  assert.equal(broken.status, 400);
  assert.equal(broken.json.code, "PERSONA_BODY_INVALID");
  assert.equal(h.read(), null, "解析失败不得落库——否则一次手滑就把语气清空了");
});
