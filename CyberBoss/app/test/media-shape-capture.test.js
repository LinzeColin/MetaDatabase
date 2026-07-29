"use strict";

// 「fixture 必须抓不能编。」
//
// message-utils 里取附件的那段代码，每个属性都试六七个备选名——url / download_url
// / cdn_url，aes_key / aeskey / aes_key_hex。这种写法本身就是"当初没抓到真的
// 响应，只好把能想到的名字都列一遍"的痕迹。这个仓为此付过代价：编出来的外部
// 响应形状让整套测试全绿，而生产 100% 失效。
//
// 所以在真正给语音做存储之前，先在线上抓一次真实形状。这一份守的是取样器本身：
// 它必须只吐结构、不吐内容——否则为了修一个存储 bug，把主人和访客说过的每一句
// 语音、发过的每一张图都写进了 journald。

const assert = require("node:assert/strict");
const test = require("node:test");

const { describeShape } = require("../src/services/inbox/durable-inbox");

test("字符串只留长度，内容一个字都不出来", () => {
  const shape = describeShape({
    text: "我今天真的很难受，不想去上班",
    url: "https://cdn.example.com/abc?key=SECRET",
  });

  assert.deepEqual(shape, { text: "string(14)", url: "string(38)" });
  const serialized = JSON.stringify(shape);
  assert.ok(!serialized.includes("难受"), "语音转写文字漏进日志了");
  assert.ok(!serialized.includes("SECRET"), "下载地址里的凭据漏进日志了");
});

test("字段名要留着——这才是抓这一次的目的", () => {
  const shape = describeShape({
    type: 3,
    voice_item: {
      text: "在吗",
      media: { encrypt_query_param: "xxxx", aes_key: "yyyy" },
      len: 12_345,
    },
  });

  assert.equal(shape.type, 3);
  assert.deepEqual(Object.keys(shape.voice_item), ["text", "media", "len"]);
  assert.deepEqual(Object.keys(shape.voice_item.media), ["encrypt_query_param", "aes_key"]);
  // 数字是元数据（长度、时长、类型），留着有用也不泄密。
  assert.equal(shape.voice_item.len, 12_345);
});

test("嵌套太深就停下，别让一条畸形消息把日志撑爆", () => {
  let deep = { leaf: "x" };
  for (let index = 0; index < 12; index += 1) {
    deep = { nested: deep };
  }

  const serialized = JSON.stringify(describeShape(deep));
  assert.ok(serialized.includes('"object"'), "深度没有截断");
  assert.ok(serialized.length < 200);
});

test("数组只取前两个，一条九图消息不该打九遍", () => {
  const shape = describeShape(["a", "bb", "ccc", "dddd"]);
  assert.deepEqual(shape, ["string(1)", "string(2)"]);
});

test("null、undefined 和函数都不会把取样器搞崩", () => {
  assert.equal(describeShape(null), null);
  assert.equal(describeShape(undefined), null);
  assert.equal(describeShape(() => {}), "function");
  assert.deepEqual(describeShape({ a: null, b: undefined }), { a: null, b: null });
});
