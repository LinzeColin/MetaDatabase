"use strict";

// 模型报的时间必须是北京时间，而且必须自证是北京时间。
//
// 2026-07-30 的真实故障：主人在悉尼 0 点问「现在几点」，助理答「悉尼时间 8 点」。
// 差的正好是东八区那 8 小时，来源是两个凑在一起的东西：
//
//   1. 机器是 UTC 的（timedatectl 显示 UTC，unit 里没有 TZ）。codex 把宿主机时区
//      原样写进模型的开场白：<current_date>2026-07-28</current_date>
//      <timezone>UTC</timezone>。这是从线上 rollout 文件里抓出来的原文。
//   2. 我们注入的时刻 [2026-07-29 22:48] 是东八区的，但不带时区。
//
// 模型被明确告知"你在 UTC"，于是把那个东八区时刻当 UTC 再换算给悉尼的用户：
// 22:48 UTC + 10 = 次日 08:48 —— 就是主人看到的"悉尼时间 8 点"。
//
// 两道闸都要在：部署时设 TZ 让 codex 的开场白改口，注入的时刻自己写上时区。
// 只修一边都还留着一条能错的路。

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { assembleRuntimeTurnText } = require("../src/core/inbound-turn");
const { SystemMessageDispatcher } = require("../src/core/system-message-dispatcher");

// 事故当时那个时刻，原样当 fixture 用。
// UTC 14:48 = 悉尼 00:48（七月是 AEST，UTC+10）= 北京 22:48。
const INCIDENT_UTC = "2026-07-29T14:48:00.000Z";
const EXPECTED_LINE = "[2026-07-29 22:48 北京时间]";

const DEPLOY_SCRIPT = path.join(__dirname, "..", "..", "ops", "deploy-to-cloud.sh");

test("入站消息注入的时刻是北京时间，并且写明是北京时间", () => {
  const text = assembleRuntimeTurnText({
    prepared: { receivedAt: INCIDENT_UTC, originalText: "现在几点" },
  });

  assert.match(text, /\[2026-07-29 22:48 北京时间\]/);
  // 22:48 而不是 14:48：拿到的是北京时间，不是机器上的 UTC。
  assert.doesNotMatch(text, /14:48/, "14:48 是 UTC，模型不该看到机器时区的时刻");
  // 悉尼 00:48 也不行——我们只承诺北京时间这一种口径。
  assert.doesNotMatch(text, /00:48/);
});

test("主动消息/提醒注入的时刻用同一个口径", () => {
  const dispatcher = new SystemMessageDispatcher({
    queueStore: {},
    config: { workspaceId: "ws", workspaceRoot: "/srv/ws" },
    accountId: "acct",
  });

  const prepared = dispatcher.buildPreparedMessage({
    id: "sys-1",
    senderId: "wx-1",
    text: "该问候一下了",
    createdAt: INCIDENT_UTC,
  });

  assert.match(prepared.text, /\[2026-07-29 22:48 北京时间\]/);
  assert.doesNotMatch(prepared.text, /14:48/);
});

test("两条路注入的第一行必须一模一样，不能各写各的", () => {
  // 同一个时刻走两条路进模型，措辞不一致的话模型会以为是两个时区。
  const inbound = assembleRuntimeTurnText({
    prepared: { receivedAt: INCIDENT_UTC, originalText: "在吗" },
  });
  const dispatcher = new SystemMessageDispatcher({
    queueStore: {},
    config: { workspaceId: "ws", workspaceRoot: "/srv/ws" },
    accountId: "acct",
  });
  const system = dispatcher.buildPreparedMessage({
    id: "sys-2", senderId: "wx-1", text: "触发", createdAt: INCIDENT_UTC,
  });

  assert.equal(inbound.split("\n")[0], EXPECTED_LINE);
  assert.equal(system.text.split("\n")[0], EXPECTED_LINE);
});

test("时区标签是跟着时刻走的，不是硬写死的一句话", () => {
  // 换一个时刻还得对。北京 2026-01-01 08:00 = UTC 2026-01-01 00:00。
  const text = assembleRuntimeTurnText({
    prepared: { receivedAt: "2026-01-01T00:00:00.000Z", originalText: "早" },
  });
  assert.match(text, /\[2026-01-01 08:00 北京时间\]/);
});

test("部署时把 TZ 写进 EnvironmentFile，codex 的开场白才会改口", () => {
  const script = fs.readFileSync(DEPLOY_SCRIPT, "utf8");

  // 必须落在写 $LIVE_ENV 的那个 heredoc 里。写在别处（比如 Environment=）会被
  // 已有的 EnvironmentFile 盖掉——这条坑脚本自己的注释里记着，别再踩一次。
  const start = script.indexOf("sudo tee $LIVE_ENV >/dev/null <<EOF");
  assert.notEqual(start, -1, "找不到写 LIVE_ENV 的 heredoc，这个断言已经失效了");
  const end = script.indexOf("\nEOF", start);
  assert.notEqual(end, -1);
  const envBody = script.slice(start, end);

  assert.match(envBody, /^TZ=Asia\/Shanghai$/m);
});
