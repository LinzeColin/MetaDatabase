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
const { UserAdmissionService } = require("../src/core/user-admission");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { WorkspaceRegistry } = require("../src/core/workspace-registry");

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
  assert.match(transcript, /第一个给它发消息的人就是主人/);
  assert.match(transcript, /发「邀请」/);

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

  // 这串码真的能用：朋友发过来就进入同意环节。
  const friend = admission.admit({ botAccountRef: "bot", senderRef: "friend", text: code });
  assert.equal(friend.route, "reply");
  assert.match(friend.text, /同意并开始/);

  // 普通用户说「邀请」只会拿到普通帮助，不会拿到码，也不会知道有这个口令。
  admission.admit({ botAccountRef: "bot", senderRef: "friend", text: "同意并开始" });
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
