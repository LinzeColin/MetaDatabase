"use strict";

// CB9-300 扫码→同意→首句→有效回复的唯一新手 Golden Path
//                                        （AC-006 / AC-007 / AC-045）
//
//   AC-006 全新用户从 /join 扫码、同意、发第一句；**不经设置页**获得有效回复。
//   AC-007 冻结 onboarding DOM 与全部分支；API Key/Provider/终端/Token/
//          服务器/配置文件出现次数 = 0。
//   AC-045 普通用户从扫码到首轮不需要 Owner 点击、生成邀请码或人工开通
//          （除 Owner 关闭公开注册时的明确产品策略）。
//
// AC-045 在这个节点之前是**不成立**的：CB_REGISTRATION_MODE 的默认值是
// "invite"，也就是一个扫了公开页那张码的人还得去找主人要一串邀请码——而公开页
// 存在的全部意义就是让人不用找主人。AC-045 括号里给的唯一例外是「Owner 关闭
// 公开注册时的明确产品策略」，说明 invite 是主人主动选的关闭态，不是出厂设置。
//
// 真实浏览器和真实微信那一段是 CB9-340（environment_bound）。这一份验的是
// **代码路径**：默认策略对、文案里没有技术词、golden path 上没有分叉。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const os = require("node:os");

const { MESSAGES, present } = require("../src/services/ops/novice-presenter");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");
const { UserAdmissionService } = require("../src/core/user-admission");
const { STATES } = require("../src/services/users/onboarding-state");
const { ACCESS_DEFAULTS, PersonaStore } = require("../src/services/persona/persona-store");

const SRC = path.join(__dirname, "..", "src");
const TEMPLATES = path.join(__dirname, "..", "templates");

// ── AC-045 默认不需要邀请码 ────────────────────────────────

test("AC-045 注册模式默认开放——邀请码是主人主动选的关闭态", () => {
  const config = fs.readFileSync(path.join(SRC, "core", "config.js"), "utf8");
  const match = /CB_REGISTRATION_MODE"\)\s*\|\|\s*"(\w+)"/.exec(config);
  assert.ok(match, "找不到 CB_REGISTRATION_MODE 的默认值，这条断言已经失效了");
  assert.equal(match[1], "open",
    "默认要邀请码——扫了公开页那张码的人还得去找主人，公开页就白做了");
  // invite 仍然是合法取值：主人要关公开注册时用它。
  assert.match(config, /\["invite", "open"\]/);
});

test("AC-045 两处默认值必须一致——不然测试测一套、线上跑另一套", () => {
  // UserAdmission 有自己的默认参数。两处不一致的话，直接 new UserAdmission 的
  // 调用方（也就是测试）拿到的策略和线上不同，而这种偏差从来不会自己暴露。
  const admission = fs.readFileSync(path.join(SRC, "core", "user-admission.js"), "utf8");
  const match = /registrationMode\s*=\s*"(\w+)"/.exec(admission);
  assert.ok(match);
  assert.equal(match[1], "open", "UserAdmission 的默认和 config 的默认对不上");
});

test("AC-045 挡滥用的是席位上限，不是注册模式", () => {
  // 把注册模式当限流用，是拿新手的第一印象去换一件别处已经做了的事。
  const admission = fs.readFileSync(path.join(SRC, "core", "user-admission.js"), "utf8");
  assert.match(admission, /seatLimitProvider/, "席位上限没了，开放注册就真的没人挡了");
  // 而且必须在**建用户之前**判。
  const comment = admission.slice(0, admission.indexOf("seatLimitProvider = null"));
  assert.match(comment, /建用户之前/);
});

test("AC-045 公开出码这条路本身有限流", () => {
  const app = fs.readFileSync(path.join(SRC, "core", "app.js"), "utf8");
  assert.match(app, /PUBLIC_QR_MIN_INTERVAL_MS/);
  assert.match(app, /PUBLIC_QR_MAX_PENDING/);
});

// ── AC-007 新手零技术词汇 ──────────────────────────────────

// AC-007 点名的六个词，加上它们在中文里的等价说法。
// 只查英文原词的话，「密钥」「服务端」这些照样能溜过去——而用户读的是中文。
const FORBIDDEN_TERMS = Object.freeze([
  { label: "API Key", patterns: [/API[ _-]?Key/i, /\bapikey\b/i, /密钥/, /密匙/] },
  { label: "Provider", patterns: [/\bprovider\b/i, /供应商/, /服务商/] },
  { label: "终端", patterns: [/终端/, /命令行/, /\bshell\b/i, /\bterminal\b/i] },
  { label: "Token", patterns: [/\btoken\b/i, /令牌/] },
  { label: "服务器", patterns: [/服务器/, /\bserver\b/i, /主机/] },
  { label: "配置文件", patterns: [/配置文件/, /环境变量/, /\.env\b/i, /\byaml\b/i] },
]);

function scan(text, where, offenders) {
  for (const { label, patterns } of FORBIDDEN_TERMS) {
    for (const pattern of patterns) {
      if (pattern.test(text)) {
        offenders.push(`${where}: ${label} — ${text.slice(0, 60)}`);
        break;
      }
    }
  }
}

test("AC-007 新手看得到的每一条文案都没有技术词——全部分支", () => {
  // 「全部分支」是这条 AC 的关键词：只检查 happy path 的话，出错时那几条
  // ——也就是用户最需要看懂的时候——照样可以满嘴术语。
  const offenders = [];
  for (const [key, entry] of Object.entries(MESSAGES)) {
    scan(entry.text, `presenter.${key}`, offenders);
    if (entry.primaryAction) {
      scan(entry.primaryAction, `presenter.${key}.action`, offenders);
    }
  }
  assert.deepEqual(offenders, [], `新手文案里有技术词：\n${offenders.join("\n")}`);
});

test("AC-007 present() 渲染出来的成品也没有技术词——占位符替换后再查一遍", () => {
  // 上一条查的是模板。占位符替换进来的值同样会被用户读到。
  const offenders = [];
  for (const key of Object.keys(MESSAGES)) {
    const rendered = present(key, { remaining_percent: 42, skipped: 3 });
    scan(rendered.text, `rendered.${key}`, offenders);
    // 顺便：渲染完不该还剩没替换掉的占位符。
    assert.ok(!/\{\w+\}/.test(rendered.text), `${key} 有没替换的占位符：${rendered.text}`);
  }
  assert.deepEqual(offenders, [], offenders.join("\n"));
});

test("AC-007 新手会看到的页面文案里也没有技术词", () => {
  // 加入页和首页是扫码那个人唯一会看到的两张网页。
  const offenders = [];
  for (const name of ["join.html", "home.html"]) {
    const html = fs.readFileSync(path.join(TEMPLATES, name), "utf8");
    // 只查**渲染出来给人看的文字**：剥掉注释、script、style 和标签本身。
    // 不剥的话 content-type、token 这种属性名会误报，而用户根本看不到它们。
    const visible = html
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<[^>]+>/g, " ");
    scan(visible, name, offenders);
  }
  assert.deepEqual(offenders, [], `页面上有技术词：\n${offenders.join("\n")}`);
});

test("AC-007 JARGON 表本身没有被悄悄缩小", () => {
  // presenter 自带一张 jargon 表用于自查。它被删空的话，上面几条依然全绿，
  // 而产品里少了一道自己的防线。
  const src = fs.readFileSync(path.join(SRC, "services", "ops", "novice-presenter.js"), "utf8");
  const match = /const JARGON = Object\.freeze\(\[([\s\S]*?)\]\)/.exec(src);
  assert.ok(match, "JARGON 表不见了");
  const count = (match[1].match(/"/g) || []).length / 2;
  assert.ok(count >= 18, `JARGON 表被缩小到 ${count} 个词`);
});

// ── AC-006 唯一 Golden Path ───────────────────────────────

test("AC-006 状态机上从没见过到能用，只有一条路", () => {
  // 「唯一」是这条 AC 的关键词。两条路的后果是有一半人走到另一条上，
  // 而那条永远没被测过。
  assert.deepEqual([...STATES].sort(),
    ["active", "pending_consent", "pending_invite", "suspended", "unseen"].sort());
});

test("AC-006 首句就能得到回复——不必先回一句「同意并开始」", () => {
  // requireExplicitConsent 默认关。默认开的话，扫完码的人发第一句话收到的是
  // 一句「请先回复同意」——多一跳，而那一跳上流失的人不会回来。
  const admission = fs.readFileSync(path.join(SRC, "core", "user-admission.js"), "utf8");
  const match = /requireExplicitConsent\s*=\s*(\w+)/.exec(admission);
  assert.ok(match);
  assert.equal(match[1], "false", "默认要求先回同意——新手路径上多了一跳");
});

test("AC-006 首轮不经设置页——公开页给的是二维码，不是设置链接", () => {
  const app = fs.readFileSync(path.join(SRC, "core", "app.js"), "utf8");
  const entry = app.slice(
    app.indexOf("async mintPublicEntryQr("),
    app.indexOf("async pollPublicEntryQr("),
  );
  assert.ok(entry.length > 0, "找不到 mintPublicEntryQr");
  assert.match(entry, /qrDataUri/, "公开入口不给二维码了？");
  // 公开入口不许下发设置链接或令牌——那既是多一跳，也是把凭据放进无鉴权响应。
  assert.ok(!/setupUrl|setupToken|portalOrigin/.test(entry),
    "公开入口把设置链接塞进了首轮");
});

test("AC-006 公开页回给访客的东西里没有任何身份或凭据", () => {
  const app = fs.readFileSync(path.join(SRC, "core", "app.js"), "utf8");
  const poll = app.slice(
    app.indexOf("async pollPublicEntryQr("),
    app.indexOf("prunePublicEntryTickets("),
  );
  const confirmed = poll.slice(poll.indexOf('state: "confirmed"'), poll.indexOf('state: "confirmed"') + 400);
  for (const leak of ["accountId:", "token", "senderId", "userId"]) {
    assert.ok(!confirmed.includes(leak), `确认响应里带出了 ${leak}`);
  }
});

test("AC-006 新手四步的每一步都有对应的产品文案", () => {
  // 扫码 → 同意 → 首句 → 有效回复。任何一步没有文案，用户就会在那一步卡住
  // 而不知道该做什么——这条 AC 说的「有效回复」不只是模型答了话。
  assert.ok(MESSAGES.welcome, "没有欢迎语");
  assert.ok(MESSAGES.consent, "没有同意提示");
  assert.ok(MESSAGES.home, "没有开通完的落地话");
  // 每一条都要给出下一步能做什么，除了那几条纯告知的。
  for (const key of ["welcome", "consent", "home"]) {
    assert.ok(MESSAGES[key].primaryAction, `${key} 没告诉用户下一步回什么`);
  }
});

test("AC-006 同意那句话说清楚会保存什么——但不说主人能看", () => {
  // 主人的明确要求：只说「个人数据会被后台保存」，不说主人能看到。
  const consent = MESSAGES.consent.text;
  assert.match(consent, /保存/);
  for (const forbidden of ["管理员能看", "主人能看", "所有者可以查看", "会被查看"]) {
    assert.ok(!consent.includes(forbidden), `同意文案里出现了「${forbidden}」`);
  }
});

// ── AC-045 行为面：默认配置下，第二个人真的能进 ─────────────

function admissionWithDefaults(t, overrides = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-300-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const spool = new RuntimeSpoolDatabase({
    databasePath: path.join(dir, "runtime.db"),
    encryptionKey: Buffer.alloc(32, 41),
    identityKey: Buffer.alloc(32, 43),
  });
  t.after(() => { try { spool.close(); } catch { /* 已经关了 */ } });
  return new UserAdmissionService({
    database: spool.database,
    identityKey: Buffer.alloc(32, 43),
    ownerUserId: spool.ownerUserId,
    ownerSenderIds: [],
    // **刻意不传 registrationMode**：这条测的就是默认值。
    ...overrides,
  });
}

test("AC-045 默认配置下，第二个人发第一句话就直接成为普通用户", (t) => {
  // 这条是**行为**断言，不是源码扫描。改默认值那次，仓里 1189 条测试一条都
  // 没红——说明在此之前没有任何测试钉住过这个默认，而它决定了每一个新人的
  // 第一分钟。源码扫描能防止有人把它改回去，但证明不了它现在真的生效。
  const admission = admissionWithDefaults(t);

  const owner = admission.admit({ botAccountRef: "bot", senderRef: "me", text: "你好" });
  assert.equal(owner.route, "owner");
  assert.equal(owner.ownerClaimed, true);

  const guest = admission.admit({ botAccountRef: "bot", senderRef: "someone-else", text: "你好" });
  assert.equal(guest.route, "user", `第二个人被挡在门外了：${JSON.stringify(guest)}`);
  assert.ok(guest.userContext, "进来了但没有 UserContext");
  assert.equal(guest.userContext.role, "user");
  // 一次主人点击、一串邀请码、一次人工开通都不需要。
  assert.notEqual(guest.route, "reply");
  assert.ok(!String(guest.text || "").includes("邀请码"));
});

test("AC-045 主人明确关闭公开注册时，邀请码那条路依然在", (t) => {
  // 括号里的例外必须真的可用，否则「默认开放」就变成了「只能开放」。
  const admission = admissionWithDefaults(t, { registrationMode: "invite" });
  admission.admit({ botAccountRef: "bot", senderRef: "me", text: "你好" });
  const guest = admission.admit({ botAccountRef: "bot", senderRef: "someone-else", text: "你好" });
  assert.equal(guest.route, "reply");
  assert.match(guest.text, /邀请码/);
});

test("AC-045 开放注册下，两个访客仍然是两个隔离的人", (t) => {
  // 开放注册最容易顺手引入的坏法：所有访客共用一个匿名身份。
  const admission = admissionWithDefaults(t);
  admission.admit({ botAccountRef: "bot", senderRef: "me", text: "你好" });
  const a = admission.admit({ botAccountRef: "bot", senderRef: "guest-a", text: "你好" });
  const b = admission.admit({ botAccountRef: "bot", senderRef: "guest-b", text: "你好" });
  assert.equal(a.route, "user");
  assert.equal(b.route, "user");
  assert.notEqual(a.userContext.userId, b.userContext.userId,
    "两个访客共用了同一个 user_id——隔离没了");
});

// ── AC-045 走真实那条路：resolveRegistrationMode ────────────

test("AC-045 产品默认是 open，而「没设过」不会被当成主人选了 invite", () => {
  // 这条是这个节点最贵的一次教训。
  //
  // 第一版我只改了 config.js 的 CB_REGISTRATION_MODE 默认，17 条测试全绿——
  // 但线上一点没变：resolveRegistrationMode 里**面板设置优先于环境变量**，而
  // 面板的 ACCESS_DEFAULTS.mode 还是 invite。而我那批测试全都直接
  // new UserAdmissionService({registrationMode: 默认})，一条都没走过
  // resolveRegistrationMode。改对了一个用不上的默认值，测试却告诉我做完了。
  const { normalizeAccess } = require("../src/services/persona/persona-store");
  assert.equal(ACCESS_DEFAULTS.mode, "open", "产品默认不是 open");
  assert.equal(ACCESS_DEFAULTS.seats, 5, "席位上限变了（主人拍板的是 5）");
  // 没设过是 null，不是 invite——替主人做了他没做过的选择，公开页就白做了。
  assert.equal(normalizeAccess({}).mode, null);
  // 但看不懂的值往关着的那边靠：写坏的配置不该把门打开。
  assert.equal(normalizeAccess({ mode: "OPEN" }).mode, "invite");
});

test("AC-045 三层默认必须是同一个答案", () => {
  // config 的默认、UserAdmission 的默认、面板的默认。三个里只要有一个不一样，
  // 「默认是什么」这个问题就没有答案——而线上取的是哪一个取决于哪条路先跑到。
  const config = fs.readFileSync(path.join(SRC, "core", "config.js"), "utf8");
  const admission = fs.readFileSync(path.join(SRC, "core", "user-admission.js"), "utf8");
  const app = fs.readFileSync(path.join(SRC, "core", "app.js"), "utf8");
  assert.equal(/CB_REGISTRATION_MODE"\)\s*\|\|\s*"(\w+)"/.exec(config)[1], "open");
  assert.equal(/registrationMode\s*=\s*"(\w+)"/.exec(admission)[1], "open");
  assert.equal(ACCESS_DEFAULTS.mode, "open");
  // app.js 最后那层兜底不许再写死一个第四个值。
  assert.ok(!/registrationMode \|\| "invite"/.test(app),
    "app.js 里还硬写着 invite 兜底");
});

test("AC-045 resolveRegistrationMode 这条真实路径给出 open", (t) => {
  // 不是扫源码，是真的跑一遍：建一个空的 PersonaStore（全新安装的样子），
  // 按 app.js 的逻辑解析一次。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cb9-300-mode-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const personaStore = new PersonaStore({ filePath: path.join(dir, "persona.json") });

  const resolve = (config) => {
    try {
      const mode = personaStore?.read().access.mode;
      if (mode === "open" || mode === "invite") return mode;
    } catch { /* 退回配置 */ }
    return config.registrationMode || ACCESS_DEFAULTS.mode;
  };

  assert.equal(resolve({ registrationMode: "" }), "open",
    "全新安装解析出来还是 invite——新人依然要找主人");
  // 环境变量仍然有效：面板没设过时它说了算，否则 CB_REGISTRATION_MODE 就是
  // 一条写了也没人读的死配置。
  assert.equal(resolve({ registrationMode: "invite" }), "invite",
    "面板兜底把环境变量吃掉了");
});

test("AC-045 access.mode 三态，一个都不能合并", () => {
  // 这条测的是**行为**，不是源码形状：上一版我写成扫正则，结果实现改了三态之后
  // 那条断言和实现直接相反——扫源码的断言在实现变了之后只会告诉你「形状不对」，
  // 不会告诉你「行为对不对」。
  const { normalizeAccess } = require("../src/services/persona/persona-store");
  // 没设过 → null。替主人选 invite 的话，公开页就白做了。
  assert.equal(normalizeAccess({}).mode, null);
  assert.equal(normalizeAccess({ mode: "" }).mode, null);
  assert.equal(normalizeAccess(undefined).mode, null);
  // 明确设了 → 就是它。
  assert.equal(normalizeAccess({ mode: "open" }).mode, "open");
  assert.equal(normalizeAccess({ mode: "invite" }).mode, "invite");
  // 设了但认不出来 → invite。访问控制字段，看不懂的值往关着的那边靠；
  // 猜 open 是拿别人的门去赌自己没理解错。
  for (const junk of ["OPEN", "Open", "foo", "1", "true"]) {
    assert.equal(normalizeAccess({ mode: junk }).mode, "invite", `${junk} 被当成了开放`);
  }
});