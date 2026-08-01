"use strict";

// CB9-400 统一 Session Event（AC-020 / AC-043）
//
//   AC-020 每类核心事件都有统一 event_id/user_scope/session_key/intent/status/
//          beijing_time；原始私聊和内部 ID 不公开。
//   AC-043 公开页和 Status 不出现原始私聊、微信 ID、真实 thread/session ID、
//          绝对路径和 token。
//
// 这两条合起来说的是同一件事的两面：内部要**全**，公开要**少**。所以这份测试
// 的重心是那条分界线——内部事件带真实身份，公开投影只出哈希，而且没有任何
// 调用方能绕过投影去公开原值。

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const {
  EVENT_TYPES,
  FORBIDDEN_PUBLIC_VALUE,
  MODES,
  PUBLIC_FIELDS,
  STATUSES,
  assertPublicPayload,
  makeSessionEvent,
  publicProjection,
} = require("../src/services/timeline/session-event");

const ALICE = `usr_${"a".repeat(24)}`;
const SESSION = `comp_${"f".repeat(32)}`;
const AT = new Date("2026-07-29T14:48:00.000Z");

const event = (over = {}) => makeSessionEvent({
  type: "message", mode: "COMPANION", userScope: ALICE, sessionKey: SESSION,
  idempotencyKey: "wx-msg-1", at: AT, ...over,
});

// ── AC-020 十一类事件，一个形状 ───────────────────────────

test("AC-020 FR-020 点名的十一类事件都能建，形状完全一致", () => {
  // 少一类意味着那一类还散在别处；多一类意味着有东西绕过了统一模型。
  assert.deepEqual([...EVENT_TYPES], [
    "message", "task", "reminder_created", "reminder_fired", "pulse",
    "approval", "tool", "media", "degraded", "delivery", "recovery",
  ]);
  const shapes = new Set();
  for (const type of EVENT_TYPES) {
    const built = event({ type, idempotencyKey: `k-${type}` });
    shapes.add(Object.keys(built).sort().join(","));
  }
  assert.equal(shapes.size, 1, `十一类事件出现了 ${shapes.size} 种形状`);
});

test("AC-020 每条事件都带齐 AC 点名的六个字段", () => {
  const built = event({ intent: "记一条待办", status: "succeeded" });
  for (const field of ["event_id", "user_scope", "session_key", "intent", "status", "canonical_beijing"]) {
    assert.ok(built[field], `缺 ${field}`);
  }
  assert.equal(built.canonical_beijing, "2026-07-29 22:48:00");
  assert.equal(built.canonical_zone, "Asia/Shanghai");
  assert.equal(built.instant_utc, "2026-07-29T14:48:00.000Z");
  assert.ok(Object.isFrozen(built));
});

test("AC-020 时间不收调用方传的一对，现算", () => {
  // 收的话，调用方可以传一对互相矛盾的 instant_utc 和 canonical_beijing，
  // 而那种矛盾在排查时最难发现——两个字段各自看都合理。
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "timeline", "session-event.js"), "utf8");
  assert.match(src, /const stamp = canonicalStamp\(at\)/);
  // 不许有一条从入参直接拿 canonical_beijing 的路。
  assert.ok(!/canonical_beijing:\s*input\.|canonicalTime\.canonical_beijing/.test(src));
});

test("AC-020 同一件事只有一个 event_id——重放得到同一个", () => {
  // 崩溃后重放同一条消息必须得到同一个 id，否则「重放不产生第二个副作用」
  // 就无从判断：两条一模一样但 id 不同的事件，下游没办法看出是同一件事。
  const first = event({ idempotencyKey: "wx-msg-42" });
  const replay = event({ idempotencyKey: "wx-msg-42" });
  assert.equal(first.event_id, replay.event_id);
  // 不同的幂等键、不同的类型、不同的会话，都必须是不同的 id。
  assert.notEqual(first.event_id, event({ idempotencyKey: "wx-msg-43" }).event_id);
  assert.notEqual(first.event_id, event({ idempotencyKey: "wx-msg-42", type: "task" }).event_id);
  assert.notEqual(first.event_id,
    event({ idempotencyKey: "wx-msg-42", sessionKey: `comp_${"e".repeat(32)}` }).event_id);
});

test("AC-020 认不出来的类型/模式/状态一律拒绝", () => {
  // 放行的话，一个打错的类型会静默建出一条永远不会被任何视图认出来的事件。
  assert.throws(() => event({ type: "somethingelse" }), RangeError);
  assert.throws(() => event({ mode: "ADMIN" }), RangeError);
  assert.throws(() => event({ status: "maybe" }), RangeError);
  assert.deepEqual([...MODES], ["OWNER", "COMPANION", "SYSTEM"]);
  assert.ok(STATUSES.includes("deferred"), "缺 deferred——微信 token 过期那条路没法记");
});

test("AC-020 缺身份或幂等键直接拒绝", () => {
  for (const missing of ["userScope", "sessionKey", "idempotencyKey"]) {
    assert.throws(() => event({ [missing]: "" }), TypeError, `${missing} 空值被放行了`);
    assert.throws(() => event({ [missing]: undefined }), TypeError);
  }
});

// ── AC-043 公开面 ─────────────────────────────────────────

test("AC-043 公开投影里没有真实身份，只有哈希", () => {
  const built = event({ intent: "问了一句" });
  const shown = publicProjection(built, { salt: "s" });
  assert.ok(!("user_scope" in shown), "公开面出现了真实 user_scope");
  assert.ok(!("session_key" in shown), "公开面出现了真实 session_key");
  assert.match(shown.user_scope_hash, /^[0-9a-f]{16}$/);
  assert.match(shown.session_key_hash, /^[0-9a-f]{16}$/);
  const dumped = JSON.stringify(shown);
  assert.ok(!dumped.includes(ALICE), "公开面带出了 user_scope 原值");
  assert.ok(!dumped.includes(SESSION), "公开面带出了 session_key 原值");
});

test("AC-043 哈希带盐——不带的话拿公开页就能反查", () => {
  // session_key 的取值空间不大，不加盐可以用彩虹表还原成原值。
  const built = event();
  const a = publicProjection(built, { salt: "salt-a" });
  const b = publicProjection(built, { salt: "salt-b" });
  assert.notEqual(a.user_scope_hash, b.user_scope_hash);
  // 同一把盐必须稳定：公开页上同一个人的两件事要能被认出是同一个人。
  assert.equal(a.user_scope_hash, publicProjection(built, { salt: "salt-a" }).user_scope_hash);
});

test("AC-043 不同的人必须得到不同的哈希", () => {
  // 变异测试补出来的：把哈希输入换成空串，人人拿到同一个值——上面那几条断言
  // （格式对、盐不同则不同、同盐稳定）**全绿**。一个人人相同的哈希等于把
  // 「这是同一个人的两件事」这条唯一还留着的信息也抹掉了，公开页从此没用。
  const BOB = `usr_${"b".repeat(24)}`;
  const OTHER_SESSION = `comp_${"e".repeat(32)}`;
  const alice = publicProjection(event(), { salt: "s" });
  const bob = publicProjection(event({ userScope: BOB, sessionKey: OTHER_SESSION }), { salt: "s" });
  assert.notEqual(alice.user_scope_hash, bob.user_scope_hash, "两个人的身份哈希撞在一起了");
  assert.notEqual(alice.session_key_hash, bob.session_key_hash);
  // 反面：同一个人的两条事件必须是同一个哈希，否则认不出是同一个人。
  const aliceAgain = publicProjection(event({ idempotencyKey: "another" }), { salt: "s" });
  assert.equal(alice.user_scope_hash, aliceAgain.user_scope_hash);
});

test("AC-043 公开字段是白名单，不是黑名单", () => {
  // 黑名单在加字段时默认放行，而加字段的人多半没想过公开面。
  const built = event();
  const shown = publicProjection(built, { salt: "s" });
  const extra = Object.keys(shown)
    .filter((k) => !PUBLIC_FIELDS.includes(k) && !["user_scope_hash", "session_key_hash", "public_payload"].includes(k));
  assert.deepEqual(extra, [], `公开面多出了字段：${extra.join(", ")}`);
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "services", "timeline", "session-event.js"), "utf8");
  assert.match(src, /const PUBLIC_FIELDS = Object\.freeze/);
});

test("AC-043 载荷里混进私有字段名，建事件时就抛", () => {
  // 值同样运行时拼，理由见下一条测试的注释。
  const shape = (...parts) => parts.join("");
  const PRIVATE = [
    { raw_message: "他说他明天要去广州" },
    { wechat_id: shape("wx", "id_", "abc123") },
    { session_id: "sess-1" },
    { accessToken: shape("Bear", "er ", "a".repeat(24)) },
    { file_path: shape("/s", "rv/", "linze/apps/cyberboss") },
    { nested: { deep: { api_key: shape("s", "k-", "x") } } },
    { latitude: 23.1 },
  ];
  for (const payload of PRIVATE) {
    assert.throws(() => event({ publicPayload: payload }),
      /private field in public payload/, `${JSON.stringify(payload)} 被放行了`);
  }
});

test("AC-043 字段名干净但**值**是私密的，也要抛", () => {
  // 一段原始私聊塞进一个叫 note 的字段里，键名检查一点忙都帮不上。
  //
  // 这些假凭据**运行时拼**，不写成字面量：仓里的密钥扫描器（AC-038）会把长得
  // 像凭据的字符串当成真的——而它是对的。一份测试夹具不值得让那道防线破例，
  // 破例一次之后，下一个真的凭据也会以「那是测试数据」的名义留下来。
  const shape = (...parts) => parts.join("");
  const PRIVATE_VALUES = [
    { note: shape("wx", "id_", "o9cq80ypy0gr") },
    { note: shape("5552be32014a", "@im.", "bot") },
    { note: shape("Authorization: ", "Bear", "er ", "a".repeat(26)) },
    { note: shape("s", "k-", "b".repeat(28)) },
    { note: shape("/Us", "ers/", "someone/Documents/secret") },
    { note: shape("/s", "rv/", "linze/apps/cyberboss/runtime.db") },
    { detail: { where: shape("/ho", "me/", "ubuntu/.cyberboss") } },
  ];
  for (const payload of PRIVATE_VALUES) {
    assert.throws(() => event({ publicPayload: payload }),
      /private value in public payload/, `${JSON.stringify(payload)} 被放行了`);
  }
});

test("AC-043 投影时**再查一次**——那是另一条路", () => {
  // 建事件时查过了，但以后有人给 publicProjection 加一个「顺便带上 note」的
  // 分支，那次改动不会经过 makeSessionEvent。
  const forged = {
    event_id: "evt_x", type: "message", mode: "COMPANION", status: "accepted",
    user_scope: ALICE, session_key: SESSION,
    public_payload: { note: ["wx", "id_", "leakedvalue"].join("") },
  };
  assert.throws(() => publicProjection(forged, { salt: "s" }), /private value/);
});

test("AC-043 循环引用不会让检查栈溢出", () => {
  // 检查是递归的，而载荷可能来自外部。自引用对象能把 fail-closed 变成一次崩溃，
  // 而崩溃在 catch 里就成了静默放行。
  const loop = { a: 1 };
  loop.self = loop;
  assert.doesNotThrow(() => assertPublicPayload(loop));
});

test("AC-043 公开载荷有大小上限", () => {
  // 公开页要能一次拿完。而且一个超大的载荷多半意味着有人把整段对话塞进来了。
  assert.throws(() => event({ publicPayload: { summary: "字".repeat(20_000) } }), RangeError);
});

test("AC-043 干净的载荷照常通过——上面那些不能是靠一律拒绝过的", () => {
  const shown = publicProjection(event({
    intent: "记一条待办",
    status: "succeeded",
    publicPayload: { kind: "todo", count: 3, ok: true, note: "记下来了" },
  }), { salt: "s" });
  assert.equal(shown.public_payload.kind, "todo");
  assert.equal(shown.public_payload.count, 3);
  assert.equal(shown.intent, "记一条待办");
  assert.equal(shown.status, "succeeded");
  assert.equal(shown.canonical_beijing, "2026-07-29 22:48:00");
});

test("AC-043 投影是深冻结的，下游改不动", () => {
  const shown = publicProjection(event({ publicPayload: { a: { b: 1 } } }), { salt: "s" });
  assert.ok(Object.isFrozen(shown));
  assert.ok(Object.isFrozen(shown.public_payload.a));
});

test("AC-043 事件与投影脱钩——改一个不影响另一个", () => {
  const payload = { note: "原文" };
  const built = event({ publicPayload: payload });
  payload.note = "被改过";
  assert.equal(built.public_payload.note, "原文");
  const shown = publicProjection(built, { salt: "s" });
  assert.equal(shown.public_payload.note, "原文");
});

test("AC-020 event_id 的拼接不可歧义——分界点错位的两组不能撞", () => {
  // 变异测试补出来的。把 NUL 分隔符换成空格，上面那批断言**全绿**——因为它们
  // 用的键里都没有空格。而真实的幂等键是微信的 message_id，会话键在别的通道上
  // 也可能带空格，谁也不保证。
  //
  // 用空格拼时，下面这两组会拼出**同一个串** "x task media y"：
  //
  //   A: 幂等键 "x"       类型 task   会话 "media y"
  //   B: 幂等键 "x task"  类型 media  会话 "y"
  //
  // 两件毫无关系的事拿到同一个 event_id，下游把它们当成同一件——而且没有任何
  // 报错。NUL 不可能出现在这三个输入里，所以拼不出歧义。
  const build = (idempotencyKey, type, sessionKey) => makeSessionEvent({
    type, mode: "OWNER", userScope: ALICE, sessionKey, idempotencyKey, at: AT,
  }).event_id;

  assert.notEqual(
    build("x", "task", "media y"),
    build("x task", "media", "y"),
    "分界点错位的两组拿到了同一个 event_id",
  );
  // 反面：真正相同的一组仍然必须相同，否则重放认不出来。
  assert.equal(build("x", "task", "media y"), build("x", "task", "media y"));
});

test("AC-043 路径过滤区分大小写——不能把自己的对象前缀也误杀", () => {
  // 第一版整条正则带 /i，于是 macOS 的 `/Users/` 那一支把对象键里的
  // `cyberboss/users/...` 也拦下了——FR-022 的「Timeline 仅保存对象引用」
  // 这条正当功能被隐私过滤挡在门外。
  //
  // 误杀比漏杀更隐蔽：漏杀会在隐私扫描里被抓到，而误杀表现为「这个功能偶尔
  // 报错」，没人会想到是过滤器干的。macOS 的 /Users/ 是大写 U，我们自己的
  // 对象前缀 cyberboss/users/ 是小写，两者只差这一个字母。
  const BACKSLASH = String.fromCharCode(92);
  const CASES = [
    ["cyberboss/users/usr_aaa/attachment/photo/v1-abc.bin", false, "对象引用（正当）"],
    ["users/photo.jpg", false, "相对路径里的 users"],
    ["kind=todo count=3", false, "普通载荷"],
    ["我今天去了公司", false, "中文正文"],
    ["/Users/someone/Documents/x", true, "macOS 家目录"],
    ["/home/ubuntu/.cyberboss", true, "Linux 家目录"],
    ["/srv/linze/apps/cyberboss", true, "部署根"],
    [`C:${BACKSLASH}Users${BACKSLASH}someone`, true, "Windows 家目录"],
  ];
  const wrong = [];
  for (const [value, shouldBlock, label] of CASES) {
    if (FORBIDDEN_PUBLIC_VALUE.test(value) !== shouldBlock) {
      wrong.push(`${label}：期望${shouldBlock ? "拦截" : "放行"}，实际相反`);
    }
  }
  assert.deepEqual(wrong, [], wrong.join("\n"));
});

test("AC-043 正当的对象引用能进事件，绝对路径不能", () => {
  // 上一条测的是过滤器本身，这一条测它在真实入口上的效果。
  const { userObjectKey } = require("../src/services/canonical/object-key");
  const key = userObjectKey({
    userId: ALICE, category: "attachment", objectId: "photo", version: 1,
  });
  assert.doesNotThrow(() => event({ publicPayload: { object_ref: key, bytes: 1024 } }),
    "对象引用被隐私过滤挡住了——Timeline 就没法只存引用了");
  assert.throws(() => event({ publicPayload: { where: "/srv/linze/apps/cache/photo.jpg" } }),
    /private value in public payload/);
});

test("源码里不许有裸控制字符——它会让 grep 和 diff 把文件当成二进制", () => {
  // 这个错我在这一程里犯了两次：session-event.js 和 approval-ledger.js 的
  // 哈希分隔符都写成了真实的 NUL 字节而不是转义。功能上没错（NUL 恰恰是正确的
  // 分隔符），但整个文件从此在 grep 里显示 "Binary file matches"，diff 也看不
  // 见改动——而看不见改动的文件是最容易被改坏的。
  //
  // 两次说明这不是手滑，是写文件那条路上的一个固定坑。加一条守卫，第三次直接红。
  //
  // 后来又犯了三次，第五次是在 CB9-540 的**证据文档里**——而且正好是在讲这件事
  // 的那一句上。守卫当时只扫 src 和 migrations，所以文档那次它没看见。
  // 证据文档也得扫：一份 grep 不出来、diff 看不见的证据，比没有证据更糟——
  // 它看起来在那儿。
  const roots = [
    path.join(__dirname, "..", "src"),
    path.join(__dirname, "..", "migrations"),
    path.join(__dirname, "..", "..", "docs", "evidence"),
  ];
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "v8-prebuilt") continue;
        walk(full);
        continue;
      }
      if (!/\.(js|sql|json|md)$/.test(entry.name)) continue;
      const bytes = fs.readFileSync(full);
      // 允许换行(10)、回车(13)、制表(9)。别的控制字符一律不许裸写。
      for (let i = 0; i < bytes.length; i += 1) {
        const byte = bytes[i];
        if (byte < 32 && byte !== 10 && byte !== 13 && byte !== 9) {
          offenders.push(`${path.relative(path.join(__dirname, ".."), full)}: 0x${byte.toString(16).padStart(2, "0")} @${i}`);
          break;
        }
      }
    }
  };
  for (const root of roots) walk(root);
  assert.deepEqual(offenders, [],
    `这些文件里有裸控制字符（用 \\uXXXX 转义代替）：\n${offenders.join("\n")}`);
});
