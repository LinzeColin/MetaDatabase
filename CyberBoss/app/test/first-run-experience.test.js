"use strict";

// 这一套测的不是"功能对不对"，是"一个不懂技术的人能不能用起来"。
//
// 每条断言都对应一个曾经必须由人手工完成、现在必须由软件自己完成的步骤：
// 生成密钥、写工作区配置、认主人、发邀请码、看懂错误信息。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { PassThrough } = require("node:stream");

const {
  bootstrapInstallation,
  readEnvFile,
  updateEnvFile,
} = require("../src/core/bootstrap");
const { explainError } = require("../src/core/friendly-errors");
const { looksConfigured, runSetupWizard } = require("../src/core/setup-wizard");
const { CyberbossApp } = require("../src/core/app");
const { UserAdmissionService } = require("../src/core/user-admission");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { WorkspaceRegistry } = require("../src/core/workspace-registry");
const { readConfig } = require("../src/core/config");

function tempHome(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-firstrun-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

// 记录问了什么、答了什么，这样"向导没多问技术问题"这件事是可测的。
function scriptedPrompt(answers) {
  const asked = [];
  let index = 0;
  return {
    asked,
    ask(question) {
      asked.push(question);
      return Promise.resolve(answers[index++] ?? "");
    },
    close() {},
  };
}

test("全新安装：不设任何环境变量，密钥和工作区都自动生成", (t) => {
  const home = tempHome(t);
  const stateDir = path.join(home, ".cyberboss");

  const result = bootstrapInstallation({ stateDir });

  assert.equal(result.createdAnything, true);
  assert.equal(result.encryptionKey.created, true);
  assert.equal(result.identityKey.created, true);
  assert.equal(result.workspace.created, true);

  // 两把密钥都是 32 字节，而且只有本人能读 —— 用户没有做任何事。
  for (const key of [result.encryptionKey, result.identityKey]) {
    const stat = fs.lstatSync(key.path);
    assert.equal(stat.size, 32);
    assert.equal(stat.mode & 0o077, 0, "密钥不能让同组或其他人读到");
  }

  // 生成出来的工作区配置能直接通过那套严格得出名的校验。
  const registry = new WorkspaceRegistry({
    configPath: result.workspace.path,
    workspaceBase: result.workspaceBase,
  });
  assert.equal(registry.resolve("cyberboss").root, fs.realpathSync.native(result.workspace.root));

  // 工作区落在家目录下，不需要 root 也不碰 /srv。
  assert.equal(result.workspaceBase.startsWith(stateDir), true);
});

test("再跑一次不会覆盖密钥——否则已注册的用户会全部失效", (t) => {
  const home = tempHome(t);
  const stateDir = path.join(home, ".cyberboss");

  const first = bootstrapInstallation({ stateDir });
  const before = fs.readFileSync(first.identityKey.path);
  const second = bootstrapInstallation({ stateDir });

  assert.equal(second.createdAnything, false);
  assert.equal(second.identityKey.created, false);
  assert.deepEqual(fs.readFileSync(second.identityKey.path), before);
});

test("密钥权限太松会被自动收紧，而不是让用户自己去 chmod", (t) => {
  const home = tempHome(t);
  const stateDir = path.join(home, ".cyberboss");
  const first = bootstrapInstallation({ stateDir });
  fs.chmodSync(first.identityKey.path, 0o644);

  const second = bootstrapInstallation({ stateDir });

  assert.equal(second.identityKey.repaired, true);
  assert.equal(fs.lstatSync(second.identityKey.path).mode & 0o077, 0);
});

test("向导只问能用大白话回答的问题，而且都可以直接回车跳过", async (t) => {
  const home = tempHome(t);
  const stateDir = path.join(home, ".cyberboss");
  const output = new PassThrough();
  const seen = [];
  output.on("data", (chunk) => seen.push(String(chunk)));
  const prompt = scriptedPrompt(["", "", "n"]);

  const result = await runSetupWizard({
    stateDir,
    output,
    prompt,
    now: () => new Date("2026-07-28T10:00:00.000Z"),
  });

  const transcript = seen.join("");
  // 全程一共只问三句，而且全都按回车跳过了也能装完。
  assert.equal(prompt.asked.length, 3);
  assert.equal(result.settings.CB_REGISTRATION_MODE, "invite");

  // 屏幕上不能出现这些术语——用户看不懂它们。
  for (const jargon of ["sha256", "HKDF", "sqlite", "UserContext", "env var", "workspace_config"]) {
    assert.equal(transcript.includes(jargon), false, `向导里不该出现术语：${jargon}`);
  }
  // 但必须明确告诉用户下一步做什么。
  assert.match(transcript, /扫码登录的那个微信号本身就是主人/);
  assert.match(transcript, /cyberboss invite/);

  const env = readEnvFile(result.envFile);
  assert.equal(env.get("CB_REGISTRATION_MODE"), "invite");
  assert.ok(env.get("CB_SETUP_COMPLETED_AT"));
});

test("向导拒绝填不成立的域名，而不是默默存下一个打不开的链接", async (t) => {
  const home = tempHome(t);
  const output = new PassThrough();
  const seen = [];
  output.on("data", (chunk) => seen.push(String(chunk)));
  // 第一个不是域名；第二个用户把 https:// 一起粘了进来——这不是错误，去掉即可。
  const prompt = scriptedPrompt(["我的网站", "https://boss.example.com/", "1", "n"]);

  const result = await runSetupWizard({
    stateDir: path.join(home, ".cyberboss"),
    output,
    prompt,
  });

  assert.equal(result.settings.CB_PORTAL_ORIGIN, "https://boss.example.com");
  assert.match(seen.join(""), /只填域名本身/);

  // 填了域名就必须把隧道配置一并写好，否则用户还是不知道下一步做什么。
  assert.ok(result.tunnel);
  const config = fs.readFileSync(result.tunnel.configPath, "utf8");
  assert.match(config, /hostname: boss\.example\.com/);
  assert.match(config, /service: http:\/\/127\.0\.0\.1:8787/);
  assert.match(config, /http_status:404/, "ingress 最后一条必须是兜底");
  assert.match(seen.join(""), /cloudflared tunnel create/);
});

test("装过之后再运行不会重复走向导", (t) => {
  const home = tempHome(t);
  const stateDir = path.join(home, ".cyberboss");
  bootstrapInstallation({ stateDir });

  assert.equal(looksConfigured(stateDir), false);
  updateEnvFile(path.join(stateDir, ".env"), {
    CB_SETUP_COMPLETED_AT: "2026-07-28T10:00:00.000Z",
  });
  assert.equal(looksConfigured(stateDir), true);
});

test("第一个发消息的人自动成为主人，之后来的人一律普通用户", (t) => {
  const home = tempHome(t);
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(home, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 21),
    identityKey: Buffer.alloc(32, 23),
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: Buffer.alloc(32, 23),
    ownerUserId: spool.ownerUserId,
    // 关键：没有配任何 owner sender id，用户从没查过自己的微信 id。
    ownerSenderIds: [],
    registrationMode: "invite",
  });

  const first = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "你好" });
  assert.equal(first.route, "owner");
  assert.equal(first.ownerClaimed, true);
  assert.equal(first.userContext.role, "owner");

  // 认领窗口用掉就关死了：第二个人拿到的是邀请码提示。
  const second = admission.admit({ botAccountRef: "bot", senderRef: "someone-else", text: "你好" });
  assert.equal(second.route, "reply");
  assert.match(second.text, /邀请码/);
  assert.equal(second.ownerClaimed, undefined);

  // 主人再说话依然是主人，不会被当成第二次认领。
  const again = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "在吗" });
  assert.equal(again.route, "owner");
  assert.equal(again.ownerClaimed, undefined);
});

test("主人发「邀请」直接拿到可转发的邀请码，普通用户拿不到", (t) => {
  const home = tempHome(t);
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(home, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 31),
    identityKey: Buffer.alloc(32, 37),
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: Buffer.alloc(32, 37),
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["me"],
    registrationMode: "invite",
  });

  const invited = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "邀请" });
  assert.equal(invited.route, "reply");
  const code = invited.text.match(/^[A-Za-z0-9-]{8,}$/m)[0];
  assert.match(invited.text, /转发给朋友/);
  assert.match(invited.text, /只能用一次/);

  // 这串码真的能用：朋友发过来就开通了，不用再回一句「同意并开始」。
  const friend = admission.admit({ botAccountRef: "bot", senderRef: "friend", text: code });
  assert.notEqual(friend.route, "owner", "朋友不该被当成主人");

  // 普通用户说「邀请」只会拿到普通帮助，不会拿到码，也不会知道有这个口令。
  const asUser = admission.admit({ botAccountRef: "bot", senderRef: "friend", text: "邀请" });
  assert.equal(asUser.route, "reply");
  assert.equal(/[A-Za-z0-9-]{8,}/.test(asUser.text.replace(/[^\x00-\x7f]/g, "")), false);
  assert.match(asUser.text, /设置/);
});

test("主人和普通用户拿到的是两份不同的中文帮助", (t) => {
  const home = tempHome(t);
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(home, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 41),
    identityKey: Buffer.alloc(32, 43),
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: Buffer.alloc(32, 43),
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["me"],
    registrationMode: "invite",
  });

  const ownerHelp = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "帮助" });
  assert.match(ownerHelp.text, /你是这里的主人/);
  assert.match(ownerHelp.text, /邀请/);

  const invite = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "邀请" });
  const code = invite.text.match(/^[A-Za-z0-9-]{8,}$/m)[0];
  admission.admit({ botAccountRef: "bot", senderRef: "u", text: code });
  admission.admit({ botAccountRef: "bot", senderRef: "u", text: "同意并开始" });
  const userHelp = admission.admit({ botAccountRef: "bot", senderRef: "u", text: "帮助" });

  assert.equal(userHelp.route, "reply");
  assert.doesNotMatch(userHelp.text, /主人/);
  assert.doesNotMatch(userHelp.text, /邀请/);
  assert.match(userHelp.text, /设置/);
});

test("主人发「状态」得到的是人话，不是 JSON", (t) => {
  const home = tempHome(t);
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(home, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 51),
    identityKey: Buffer.alloc(32, 53),
  });
  t.after(() => spool.close());
  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: Buffer.alloc(32, 53),
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: ["me"],
    registrationMode: "invite",
  });

  const decision = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "状态" });
  assert.equal(decision.route, "status");
  assert.equal(decision.modelCalls, 0, "看状态不该花钱");
});

test("错误信息是中文，而且每条都给出下一步该做什么", () => {
  const cases = [
    [Object.assign(new Error("workspace_config_unavailable"), { code: "workspace_config_unavailable" }), /cyberboss setup/],
    [Object.assign(new Error("RUNTIME_IDENTITY_KEY_UNAVAILABLE"), { code: "RUNTIME_IDENTITY_KEY_UNAVAILABLE" }), /密钥/],
    [Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" }), /网络/],
    [new Error("CB_PORTAL_ORIGIN must be a bare https origin"), /https:\/\//],
    // 这是没登录时真实抛出的那句话，原文还教用户敲 npm run login——对终端
    // 用户是错的指令，所以必须被整条替换掉。
    [new Error("No saved WeChat account was found. Run `npm run login` first."), /cyberboss login/],
  ];
  for (const [error, expectation] of cases) {
    const text = explainError(error);
    assert.match(text, expectation);
    assert.match(text, /怎么办：/, "每条错误都必须给出下一步");
    assert.equal(/^[\x00-\x7f]*$/.test(text), false, "错误信息必须是中文");
  }

  // 没见过的错误照实说不认识，并把原文留下——不编一个听起来合理的解释。
  const unknown = explainError(new Error("SOME_BRAND_NEW_FAILURE"));
  assert.match(unknown, /没见过的问题/);
  assert.match(unknown, /SOME_BRAND_NEW_FAILURE/);
});

test("扫码登录的那个微信号本身就是主人，认领窗口一秒都不开", (t) => {
  const home = tempHome(t);
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(home, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 81),
    identityKey: Buffer.alloc(32, 83),
  });
  t.after(() => spool.close());

  // 很多人拿自己的常用微信登录。那样他没法给自己发消息，而"第一个发消息的人
  // 是主人"会把 Owner 权限交给第一个来找他聊天的朋友。所以只要登录带回了账号
  // 自己的标识，就用它。
  const SELF = "o9cq80yp-self@im.wechat";
  const app = {
    config: { ownerSenderIds: [], stateDir: null },
    rememberOwnerSender: CyberbossApp.prototype.rememberOwnerSender,
  };
  const bound = CyberbossApp.prototype.bindOwnerFromAccount.call(app, { userId: SELF });
  assert.deepEqual(bound, [SELF]);
  assert.deepEqual(app.config.ownerSenderIds, [SELF]);

  const admission = new UserAdmissionService({
    database: spool.database,
    identityKey: Buffer.alloc(32, 83),
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: app.config.ownerSenderIds,
    registrationMode: "invite",
  });

  // 朋友先来说话，也拿不到 Owner——他拿到的是邀请码提示。
  const friend = admission.admit({ botAccountRef: "bot", senderRef: "friend", text: "你好" });
  assert.equal(friend.route, "reply");
  assert.match(friend.text, /邀请码/);
  assert.equal(friend.ownerClaimed, undefined, "认领窗口必须从来没有打开过");
});

test("已经配了 Owner 时，登录信息不会把它顶掉", () => {
  const app = {
    config: { ownerSenderIds: ["configured-owner"], stateDir: null },
    rememberOwnerSender: CyberbossApp.prototype.rememberOwnerSender,
  };
  const bound = CyberbossApp.prototype.bindOwnerFromAccount.call(app, { userId: "someone-else" });
  assert.deepEqual(bound, ["configured-owner"]);
  assert.deepEqual(app.config.ownerSenderIds, ["configured-owner"]);
});

// ── 别人已经装好的机器 ───────────────────────────────────
//
// 云服务器上，root 早就把注册表写在 /etc/cyberboss/workspaces.json、把工作区
// 开在 /srv 下面了。bootstrap 如果按"数据目录下面那个"去猜工作区根目录，猜出
// 来的值和注册表里写的对不上，校验会判定注册表为空——而注册表恰恰是那份文件
// 里唯一没有问题的东西。这一条曾经让云端的 bridge 每次启动都 exit 1。

function provisionedRegistry(t, { workspaceBase }) {
  const home = tempHome(t);
  const configPath = path.join(home, "etc", "workspaces.json");
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.mkdirSync(path.join(workspaceBase, "cyberboss"), { recursive: true });
  fs.writeFileSync(configPath, `${JSON.stringify({
    schema_version: 1,
    default_alias: "cyberboss",
    workspace_base: workspaceBase,
    workspaces: {
      cyberboss: {
        repo: "LinzeColin/MetaDatabase",
        root: path.join(workspaceBase, "cyberboss"),
        project_subpath: "CyberBoss",
        read_only: false,
        max_bytes: 4_294_967_296,
        allowed_branches: ["main", "codex/cyberboss-*"],
        sparse_paths: ["CyberBoss", ".github"],
        root_integration_paths: [".github"],
        root_integration_write: false,
        write_globs: ["CyberBoss/**"],
      },
    },
  }, null, 2)}\n`);
  return { home, configPath };
}

test("已有注册表的机器：工作区根目录以注册表为准，不按数据目录猜", (t) => {
  const workspaceBase = fs.mkdtempSync(path.join(os.tmpdir(), "cb-srv-"));
  t.after(() => fs.rmSync(workspaceBase, { recursive: true, force: true }));
  const { home, configPath } = provisionedRegistry(t, { workspaceBase });
  const stateDir = path.join(home, "state");

  const previousConfig = process.env.CYBERBOSS_WORKSPACE_CONFIG;
  const previousBase = process.env.CYBERBOSS_WORKSPACE_BASE;
  process.env.CYBERBOSS_WORKSPACE_CONFIG = configPath;
  delete process.env.CYBERBOSS_WORKSPACE_BASE;
  t.after(() => {
    if (previousConfig === undefined) delete process.env.CYBERBOSS_WORKSPACE_CONFIG;
    else process.env.CYBERBOSS_WORKSPACE_CONFIG = previousConfig;
    if (previousBase === undefined) delete process.env.CYBERBOSS_WORKSPACE_BASE;
    else process.env.CYBERBOSS_WORKSPACE_BASE = previousBase;
  });

  const result = bootstrapInstallation({ stateDir });

  assert.equal(result.workspaceBase, workspaceBase);
  assert.equal(result.workspace.created, false, "已有的注册表不能被覆盖");
  assert.equal(process.env.CYBERBOSS_WORKSPACE_BASE, workspaceBase);

  // 真正的判据：注册表能被加载器接受。上一版在这里抛 workspace_config_empty。
  const registry = new WorkspaceRegistry({
    configPath,
    workspaceBase: process.env.CYBERBOSS_WORKSPACE_BASE,
  });
  assert.equal(registry.defaultAlias, "cyberboss");
});

test("已有注册表的机器：.env 里过期的工作区根目录会被改正", (t) => {
  const workspaceBase = fs.mkdtempSync(path.join(os.tmpdir(), "cb-srv2-"));
  t.after(() => fs.rmSync(workspaceBase, { recursive: true, force: true }));
  const { home, configPath } = provisionedRegistry(t, { workspaceBase });
  const stateDir = path.join(home, "state");
  fs.mkdirSync(stateDir, { recursive: true });
  // 上一版留下来的错值：不改正的话，它会活过每一次重启。
  updateEnvFile(path.join(stateDir, ".env"), {
    CYBERBOSS_WORKSPACE_BASE: path.join(stateDir, "workspaces"),
  });

  const previousConfig = process.env.CYBERBOSS_WORKSPACE_CONFIG;
  process.env.CYBERBOSS_WORKSPACE_CONFIG = configPath;
  delete process.env.CYBERBOSS_WORKSPACE_BASE;
  t.after(() => {
    if (previousConfig === undefined) delete process.env.CYBERBOSS_WORKSPACE_CONFIG;
    else process.env.CYBERBOSS_WORKSPACE_CONFIG = previousConfig;
    delete process.env.CYBERBOSS_WORKSPACE_BASE;
  });

  bootstrapInstallation({ stateDir });

  assert.equal(
    readEnvFile(path.join(stateDir, ".env")).get("CYBERBOSS_WORKSPACE_BASE"),
    workspaceBase,
  );
});

// ── 配了域名的机器 ───────────────────────────────────────
//
// 只要 CB_PORTAL_ORIGIN 有值，initializeDurableInbox 就会去构造 setupPortal。
// 之前这段代码排在 userTurnRuntime 之前，读 this.userTurnRuntime.vault 时它还是
// null，构造直接抛错，bridge 起不来。没配域名的机器永远走不到那一行，所以本机
// 怎么跑、模块测试怎么过，都看不出问题。
//
// 这两条走的是真正的入口路径：bootstrap → readConfig → new CyberbossApp，
// 和 index.js 里 `cyberboss start` 做的事一模一样。

function bootAppFromEnv(t, { portalOrigin }) {
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
  set("CB_MULTI_USER", "true");
  set("CB_REGISTRATION_MODE", "invite");
  set("CB_PORTAL_ORIGIN", portalOrigin);
  set("CB_RUNTIME_DB", path.join(stateDir, "runtime.db"));
  // canonical 同步需要一整套云端才有的目录，和这条测试要证的事无关。关掉它要
  // 走配置里那个明确的非生产开关，这本身也说明这条路径不会被误用到线上。
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

test("配了域名时，设置页面能构造出来（而不是在 vault 上抛空指针）", (t) => {
  const app = bootAppFromEnv(t, { portalOrigin: "https://boss.example.com" });

  assert.ok(app.userTurnRuntime, "userTurnRuntime 必须先建好");
  assert.ok(app.setupPortal, "配了域名就必须建出 setupPortal，否则后台页面永远起不来");
});

test("没配域名时不建设置页面，其余照常", (t) => {
  const app = bootAppFromEnv(t, { portalOrigin: "" });

  assert.equal(app.setupPortal, null);
  assert.ok(app.userAdmission, "没有域名不影响开通流程");
});
