"use strict";

// 出网前的最后一道隐私闸（CB9-520 / AC-020、AC-026、AC-033、AC-043、NFR-003）。
//
// AC-043 的原话：「公开页和 Status 不出现原始私聊、微信 ID、真实 thread/session
// ID、绝对路径和 token。」
//
// 这条早就有过滤器了——session-event 里的 assertPublicPayload，写得也对。问题
// 是**真实链路上没人调它**：它只在 Timeline 自己那份投影里跑。于是隐私保证的
// 形状是「我们有一个很好的过滤器」+「碰巧现在没人往公开面塞脏东西」，而后半句
// 是行为保证，下一个人加一行就没了。
//
// 这个仓在同一个形状上栽过很多次：写了守卫、守卫没接上、单测全绿。所以这里的
// 做法不是再加一个过滤器，而是把已有那个**放到唯一的出口上**——HTTP 响应只能
// 从 #json 出去，#json 一定过这道闸，于是「往公开面塞脏东西」这件事在结构上就
// 做不到了，不需要谁记得调用。
//
// 复用 session-event 的 FORBIDDEN_PUBLIC_KEYS / FORBIDDEN_PUBLIC_VALUE，不另写
// 一份。另写一份的话两份迟早不一致，而不一致的那天，哪一份在守哪个出口没人说
// 得清。

const {
  FORBIDDEN_PUBLIC_KEYS,
  FORBIDDEN_PUBLIC_VALUE,
  assertPublicPayload,
} = require("../timeline/session-event");

class PublicEgressError extends Error {
  constructor(code, pointer) {
    super(code);
    this.name = "PublicEgressError";
    this.code = code;
    // 只带路径，**永远不带值**。带值的话，一条「泄漏了」的日志本身就是那次
    // 泄漏——而它会被写进普通日志，比原来的泄漏面还大。
    this.pointer = pointer || "$";
  }
}

// 完全不鉴权的那几个出口。任何人拿到 URL 就能打开。
//
// 这几条的响应形状小而稳，所以除了值扫描之外还额外钉死**顶层键白名单**：
// 多一个键就拒。别的出口（/me、/admin）是鉴权后给本人/主人看的，形状会随功能
// 长，钉键白名单会变成每加一个功能就要改两处的负担——那种守卫最后一定会被
// 顺手放宽。它们只过值扫描和键黑名单。
//
// 这几张表是**照着真实响应抄的**，不是照着我以为的形状写的。第一版是凭印象编
// 的（qr / expiresAt / hint），结果整条公开入口被自己的隐私闸拦下——正当字段
// 全在白名单外。编出来的形状让守卫看起来在工作，实际是在拦自己。
const UNAUTHENTICATED_SURFACES = Object.freeze({
  // ok/ready/status/ticket/qrDataUri/message 来自 mintPublicEntryQr；
  // open/full 是公开页配额提示用的；code 是 404 和被拦下时那条。
  "/api/join": Object.freeze([
    "ok", "ready", "status", "ticket", "qrDataUri", "message", "open", "full", "code",
  ]),
  "/api/join/status": Object.freeze(["ok", "state", "message", "code"]),
  "/api/join/timezone": Object.freeze(["ok", "code"]),
});

// thread / session 的真实 ID。
//
// 这一条 session-event 的值过滤器里没有，因为那一层的 ID 本来就是投影过的。
// 到了 HTTP 出口就不一样了：任何一个处理函数都可能顺手把内部 ID 放进响应，
// 而它是能跨请求关联到具体某个人的——AC-043 单独点了它的名。
//
// 形状取自这个仓自己发的 ID：thread_ / sess_ / wsess_ / tok_ 前缀加长随机段。
const INTERNAL_ID_SHAPE =
  /\b(?:thread|sess|wsess|session|tok|setup|csrf)_[A-Za-z0-9_-]{16,}\b/;

// 「原始私聊」靠什么挡住：**顶层键白名单**，不是长度。
//
// 第一版拿长度当判据（超过 240 字就算没投影过）。它当场就误杀了公开入口的
// 二维码——qrDataUri 是一整张 SVG 的 data URI，几千字符，正当得不能再正当。
//
// 而且长度这条判据本身就错：/admin 上主人读对话、/me 上本人读自己的东西，
// 长文本正是那两个出口存在的理由。一条会把主路径拦下的守卫，最后一定会被
// 谁「先注释掉看看」，然后再也没打开。
//
// 真正精确的做法是按出口分：完全不鉴权的那几个出口钉死顶层键，能出去的字段
// 就那几个我们自己写的文案；鉴权后的出口本来就该给本人看他自己的内容。

// 无论哪个出口都不许出现的字段名。
//
// 和 session-event 那份完整黑名单分开：那份是给 Timeline 公开投影写的，里面有
// text / content / body——而后台对话页和「我的主页」的意义就是显示这个人自己的
// text，所以那份只在完全不鉴权的出口上跑。
//
// 但这几个不一样，它们在**任何**出口上都不该出现：
//   坐标和 IP——FR-021 说这个产品根本不采集精确位置，那么它也就没有理由出现在
//   任何一份响应里。主人自己那一页也不该有他自己的经纬度，因为我们压根没存过。
//   凭据——不解释。
//
// 这一条是红队测试发现的：把黑名单收窄到不鉴权出口之后，`{latitude: 31.23}`
// 在 /me 和 /admin 上畅通无阻。收窄收对了，但收过头了。
const NEVER_ALLOWED_KEYS = Object.freeze(new Set([
  "latitude", "longitude", "lat", "lng", "lon", "coords", "coordinates",
  "accuracy", "altitude", "geo", "gps",
  "raw_ip", "ip", "ip_address", "client_ip", "remote_addr",
  "api_key", "apikey", "secret", "password", "private_key",
  "access_token", "refresh_token", "context_token", "setup_token",
]));

function normalizeEgressKey(key) {
  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function scan(value, pointer, seen) {
  if (value === null || value === undefined) {
    return;
  }
  if (typeof value === "string") {
    if (INTERNAL_ID_SHAPE.test(value)) {
      throw new PublicEgressError("EGRESS_INTERNAL_ID", pointer);
    }
    if (FORBIDDEN_PUBLIC_VALUE.test(value)) {
      throw new PublicEgressError("EGRESS_PRIVATE_VALUE", pointer);
    }
    return;
  }
  if (typeof value !== "object") {
    return;
  }
  if (seen.has(value)) {
    return;
  }
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((item, index) => scan(item, `${pointer}[${index}]`, seen));
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (NEVER_ALLOWED_KEYS.has(normalizeEgressKey(key))) {
      throw new PublicEgressError("EGRESS_PRIVATE_FIELD", `${pointer}.${key}`);
    }
    scan(child, `${pointer}.${key}`, seen);
  }
}

// 一份响应能不能出网。
//
// 分两层，因为「公开」有两种：
//
//   完全不鉴权的出口（/api/join 那几条）—— 任何人拿到 URL 就能看。值扫描 +
//   键黑名单 + 顶层键白名单，三道全上。
//
//   鉴权后的出口（/me、/admin）—— 给本人看他自己的东西、给主人看他自己的机器。
//   只上值扫描。套键黑名单会把后台对话页清空（那份清单里有 text/content/body，
//   而显示 text 正是那一页的意义），而且只有线上才看得出来。
//
// 顺序也要紧：先值扫描再白名单。反过来的话，一个既带 wxid 又多一个键的 payload
// 会报「多了个字段」，而真正的问题是它带了微信 ID——排查的人会去改字段名。
function assertPublicEgress(payload, { surface = null } = {}) {
  // 一、值扫描。这几样在**任何**出口上都不该出现，鉴权与否无关：
  // 微信 ID、绝对路径、密钥、内部 thread/session ID。主人自己那一页也不该有
  // 服务器的文件系统布局。
  scan(payload, "$", new WeakSet());

  const allowed = surface ? UNAUTHENTICATED_SURFACES[surface] : null;
  if (!allowed) {
    // 鉴权后的出口到此为止。
    //
    // **不跑 session-event 的键黑名单。** 那份清单是给 Timeline 的公开投影写
    // 的，里面有 text / content / body —— 而后台对话页和「我的主页」的全部意义
    // 就是把这个人自己的 text 显示给他看。套上去等于把后台对话那一栏清空，
    // 而且线上才看得出来：没有一条测试用真 HTTP 打过那条路由。
    //
    // 这一刀差点就砍下去了。抓到它的不是推理，是去读了真实响应的字段名。
    return payload;
  }

  // 二、完全不鉴权的出口，再加两道。
  try {
    assertPublicPayload(payload);
  } catch (error) {
    // session-event 的两种违规要分开报：字段名不该出现，和值看起来是私密的，
    // 修法完全不同（前者改字段，后者改内容）。归成一个 code 的话，排查的人
    // 会照着错误的方向改。
    const raw = String(error?.message || "");
    const pointer = raw.replace(/^.*? at /, "") || "$";
    throw new PublicEgressError(
      raw.startsWith("private value") ? "EGRESS_PRIVATE_VALUE" : "EGRESS_PRIVATE_FIELD",
      pointer,
    );
  }
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const extra = Object.keys(payload).filter((key) => !allowed.includes(key));
    if (extra.length > 0) {
      throw new PublicEgressError("EGRESS_FIELD_NOT_ALLOWED", `$.${extra[0]}`);
    }
  }
  return payload;
}

// 这个出口是不是完全不鉴权的那一类。
function isUnauthenticatedSurface(pathname) {
  return Object.prototype.hasOwnProperty.call(UNAUTHENTICATED_SURFACES, String(pathname || ""));
}

module.exports = {
  FORBIDDEN_PUBLIC_KEYS,
  NEVER_ALLOWED_KEYS,
  INTERNAL_ID_SHAPE,
  PublicEgressError,
  UNAUTHENTICATED_SURFACES,
  assertPublicEgress,
  isUnauthenticatedSurface,
};
