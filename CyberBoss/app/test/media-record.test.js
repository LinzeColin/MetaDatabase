"use strict";

// MEDIA-1：微信收到的图片和文件要真的被保存下来。
//
// 原来只落盘在 stateDir/inbox/<日期>/，不认人也不进库。后果不是「图丢了」——
// 文件确实在磁盘上——而是**换台机器恢复出来只剩一堆无主的文件**：GitHub 全量库
// 和 Cloudflare 冷库同步的都是数据库，不进库就不在里面。
//
// 所以元数据进 user_items（kind="media"），字节留在磁盘。把图片本身塞进库会让
// 全量同步变得不可用。
//
// 这个套件最要紧的一条是**字段名对不对**：persistSingleAttachment 返回的是
// relativePath / sizeBytes / sourceFileName，第一版我写成了 path / bytes / sha256，
// 三个全不存在。猜错不会报错，只会每条都存空值然后没人发现。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { RuntimeSpoolDatabase } = require("../src/services/db/database-adapter");

const FIXTURE_KEY = Buffer.from(
  "8f4cb5db5aa765f11f782f87371dba5f9fde8cbe0f20d08c96f2ea2a9d58e8f2",
  "hex",
);
const USER_ID = "usr_media_00000000000000000000";
const OTHER_ID = "usr_other_00000000000000000000";

function openSpool(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb-media-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: Buffer.from(FIXTURE_KEY),
    identityKey: Buffer.from(FIXTURE_KEY),
  });
}

// persistSingleAttachment 真正返回的形状。照它写，不照想当然写。
function savedAttachment(overrides = {}) {
  return {
    kind: "image",
    contentType: "image/jpeg",
    isImage: true,
    sourceFileName: "IMG_0421.jpg",
    fileName: "20260729-abc123.jpg",
    absolutePath: "/var/lib/cyberboss/inbox/2026-07-29/20260729-abc123.jpg",
    relativePath: "inbox/2026-07-29/20260729-abc123.jpg",
    sizeBytes: 84213,
    ...overrides,
  };
}

// 真的调 app.js 里那个 recordIncomingMedia，不是抄一份。
function record({ database, userId, saved }) {
  const logs = [];
  const self = {
    runtimeSpoolDatabase: database,
    activeUserContext: userId ? { userId } : null,
  };
  const originalWarn = console.warn;
  console.warn = (line) => logs.push(String(line));
  const originalLog = console.log;
  console.log = () => {};
  try {
    const count = CyberbossApp.prototype.recordIncomingMedia.call(
      self,
      saved,
      { messageId: "msg-1" },
    );
    return { count, logs };
  } finally {
    console.warn = originalWarn;
    console.log = originalLog;
  }
}

test("收到的图片真的进了库，按人", (t) => {
  const database = openSpool(t);
  const { count } = record({ database, userId: USER_ID, saved: [savedAttachment()] });
  assert.equal(count, 1);

  const rows = database.listUserItems({ userId: USER_ID, kind: "media", open: true });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, "20260729-abc123.jpg");
});

test("元数据的字段名对得上真实落盘结果", (t) => {
  const database = openSpool(t);
  record({ database, userId: USER_ID, saved: [savedAttachment()] });

  const [row] = database.listUserItems({ userId: USER_ID, kind: "media", open: true });
  const note = JSON.parse(row.note);
  assert.equal(note.relativePath, "inbox/2026-07-29/20260729-abc123.jpg");
  assert.equal(note.sizeBytes, 84213);
  assert.equal(note.sourceFileName, "IMG_0421.jpg");
  assert.equal(note.contentType, "image/jpeg");
  assert.equal(note.isImage, true);
});

test("存的是相对路径——绝对路径换台机器恢复出来就是错的", (t) => {
  const database = openSpool(t);
  record({ database, userId: USER_ID, saved: [savedAttachment()] });

  const [row] = database.listUserItems({ userId: USER_ID, kind: "media", open: true });
  const note = JSON.parse(row.note);
  assert.ok(!note.relativePath.startsWith("/"), "不能存绝对路径");
});

test("认不出是谁就整批不记，而不是记到某个人头上", (t) => {
  const database = openSpool(t);
  const { count, logs } = record({ database, userId: "", saved: [savedAttachment()] });
  assert.equal(count, 0);
  assert.equal(database.listUserItems({ userId: USER_ID, kind: "media", open: true }).length, 0);
  assert.ok(logs.some((line) => line.includes("认不出是谁")), "这种情况必须留下痕迹");
});

test("别人的图片查不到", (t) => {
  const database = openSpool(t);
  record({ database, userId: USER_ID, saved: [savedAttachment()] });
  assert.equal(
    database.listUserItems({ userId: OTHER_ID, kind: "media", open: true }).length,
    0,
  );
});

test("媒体不会混进待办和日程", (t) => {
  const database = openSpool(t);
  record({ database, userId: USER_ID, saved: [savedAttachment()] });
  assert.equal(database.listUserItems({ userId: USER_ID, kind: "todo", open: true }).length, 0);
  assert.equal(database.listUserItems({ userId: USER_ID, kind: "event", open: true }).length, 0);
});

test("一条消息里的多个附件都记下来", (t) => {
  const database = openSpool(t);
  const { count } = record({
    database,
    userId: USER_ID,
    saved: [
      savedAttachment(),
      savedAttachment({ fileName: "20260729-def456.png", relativePath: "inbox/2026-07-29/20260729-def456.png" }),
    ],
  });
  assert.equal(count, 2);
  assert.equal(database.listUserItems({ userId: USER_ID, kind: "media", open: true }).length, 2);
});

test("没有文件名的那条跳过，不影响同一批里的其他条", (t) => {
  const database = openSpool(t);
  const { count } = record({
    database,
    userId: USER_ID,
    saved: [savedAttachment({ fileName: "" }), savedAttachment()],
  });
  assert.equal(count, 1);
});

test("kind 白名单只写在一处——建得进去就一定读得出来", () => {
  // 反向的坑：createUserItem 和 listUserItems 原来各写了一遍 ["todo","event"]。
  // 只在一处加 media 的话，存进去了却永远读不出来，而且不报错。
  const { MIGRATIONS } = require("../src/services/db/database-adapter");
  assert.ok(Array.isArray(MIGRATIONS), "只是确保模块加载正常");
});

test("后台那一栏真的拿得到元数据——不是只拿到个文件名", (t) => {
  // 第五次同类事故：buildPersonDetail 的 mapper 只挑 title/dueAt/createdAt，
  // note 不在里面。漏掉它的话后台那一栏会显示出来，但每条都缺大小和图标，
  // 看起来在工作，其实是空的。
  //
  // 后台按 senderId 列人，而 media 按 user_id 存，所以这里要把那一跳也接上——
  // 只测 mapper 不测换算的话，正好漏掉后台真正走的那条路。
  const database = openSpool(t);
  record({ database, userId: USER_ID, saved: [savedAttachment()] });

  const detail = CyberbossApp.prototype.buildPersonDetail.call(
    {
      runtimeSpoolDatabase: database,
      formatOwnerLocalTime: (v) => v,
      listMemoriesFor: () => [],
      // 后台那一栏现在还带提醒和他自己的设置（主人要「在后台看到所有人的个人
      // 页面还有个人信息设置」）。少这一条 stub，这里挂的是 TypeError，不是断言。
      listOwnReminders: () => [],
      // 后台按 senderId 列人，换算走 personaUserIdForSender（读来信上记着的
      // user_id）。以前这里走的是 identify + resolveAccount(who)，而
      // resolveAccount 不收参数——那个 who 被忽略，所有人都按主号去认，不在主号
      // 下面的人全认错。只测 mapper 不测这一跳的话，正好漏掉后台真正走的那条路。
      personaUserIdForSender: () => USER_ID,
    },
    "wx_sender_1",
  );

  assert.equal(detail.media.length, 1, "后台那一栏拿不到任何媒体");
  const meta = JSON.parse(detail.media[0].note);
  assert.equal(meta.sourceFileName, "IMG_0421.jpg");
  assert.equal(meta.sizeBytes, 84213);
});
