"use strict";

// CB9-210 加入页时区上报的**整条链路**（AC-012 / AC-042）
//
// 上一份测试验的是 adapter 本身。这一份验的是它有没有真的被接上：起一个真的
// PortalServer，用真的 HTTP 请求打 /api/join/timezone，看观测有没有落到暂存里。
//
// 这个仓的招牌坏法是「模块写好了、单测全绿、没人调用」。adapter 的单测再多也
// 挡不住路由没挂、handler 名字打错、或者哪次重构把这一条从路由表里挤掉——那
// 些情况下上面那份测试依然全绿，而线上一个时区都收不到。

const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");

const { PortalHttpServer } = require("../src/services/portal/portal-server");
const {
  PendingTimezoneSignals,
  normalizeBrowserTimezone,
  readCloudflareSignals,
  safeObservation,
} = require("../src/services/location/timezone-signals");

// Cloudflare 真实会带的头，含它确实会发的 cf-connecting-ip。
const CF_HEADERS = Object.freeze({
  "cf-connecting-ip": "203.0.113.47",
  "x-forwarded-for": "203.0.113.47, 172.71.0.1",
  "cf-ipcountry": "AU",
  "cf-ipcity": "Sydney",
  "cf-timezone": "Australia/Sydney",
});

// app.js 里 recordJoinTimezoneSignal 的同一套判断。
// 这里复刻是为了把 PortalServer 单独立起来测；两边的行为由 CB9-220 的绑定测试
// 和这份的路由测试各守一半。
function makeRecorder(validTickets) {
  const pending = new PendingTimezoneSignals();
  const record = ({ ticket, timezone, headers } = {}) => {
    const key = String(ticket || "").trim();
    if (!key || !validTickets.has(key)) {
      return false;
    }
    const browser = normalizeBrowserTimezone(timezone);
    const cf = readCloudflareSignals(headers || {});
    const source = browser ? "browser_iana" : (cf.timezone ? "cloudflare_timezone" : "");
    const zone = browser || cf.timezone;
    if (!source || !zone) {
      return false;
    }
    try {
      return pending.record(key, safeObservation({
        source, timezone: zone, city: cf.city, country: cf.country,
      }));
    } catch {
      return false;
    }
  };
  return { pending, record };
}

async function withServer(record, run) {
  const server = new PortalHttpServer({
    // portal 是必填依赖，但这条路一次都不会走到它——留一个会抛错的桩，
    // 万一哪天时区上报被错误地路由进 #handleApi，测试会立刻炸而不是假绿。
    portal: { handle: () => { throw new Error("时区上报不该走 portal.handle"); } },
    port: 0, host: "127.0.0.1", joinTimezoneSignal: record,
  });
  const address = await server.start();
  const port = typeof address === "object" && address
    ? address.port
    : Number(String(address).split(":").pop());
  try {
    await run(port);
  } finally {
    if (typeof server.stop === "function") {
      await server.stop();
    }
  }
}

function post(port, body, headers = {}) {
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  return new Promise((resolve) => {
    const request = http.request({
      host: "127.0.0.1", port, path: "/api/join/timezone", method: "POST",
      headers: {
        "content-type": "application/json",
        "content-length": Buffer.byteLength(payload),
        ...headers,
      },
    }, (response) => {
      let raw = "";
      response.on("data", (chunk) => { raw += chunk; });
      response.on("end", () => resolve({ status: response.statusCode, body: raw }));
    });
    request.on("error", () => resolve({ status: 0, body: "" }));
    request.end(payload);
  });
}

test("AC-012 真实 HTTP 请求能把浏览器时区送进暂存", async () => {
  const { pending, record } = makeRecorder(new Set(["real-ticket"]));
  await withServer(record, async (port) => {
    const response = await post(port, { ticket: "real-ticket", timezone: "Australia/Sydney" }, CF_HEADERS);
    assert.equal(response.status, 200);
    assert.deepEqual(JSON.parse(response.body), { ok: true });

    const observation = pending.take("real-ticket");
    assert.ok(observation, "路由通了但观测没落地——这条链路断了");
    assert.equal(observation.source, "browser_iana");
    assert.equal(observation.timezone, "Australia/Sydney");
    assert.equal(observation.city, "Sydney");
    assert.equal(observation.country, "AU");
    // 全链路走完，原始 IP 一个字节都不能出现在观测里。
    const dumped = JSON.stringify(observation);
    for (const leak of ["203.0.113.47", "172.71.0.1"]) {
      assert.ok(!dumped.includes(leak), `观测里带出了 ${leak}`);
    }
  });
});

test("AC-012 浏览器报了个认不出来的时区，退到 Cloudflare 佐证", async () => {
  const { pending, record } = makeRecorder(new Set(["real-ticket"]));
  await withServer(record, async (port) => {
    await post(port, { ticket: "real-ticket", timezone: "Mars/Olympus" }, CF_HEADERS);
    const observation = pending.take("real-ticket");
    assert.ok(observation, "浏览器信号无效时应退到 Cloudflare");
    assert.equal(observation.source, "cloudflare_timezone");
    assert.equal(observation.timezone, "Australia/Sydney");
    // 佐证的置信度必须低于浏览器，否则 CB9-220 不会去问那句确认。
    assert.ok(observation.confidence < 0.8);
  });
});

test("AC-012 无任何信号时接口照样成功——首条回复不能被时区卡住", async () => {
  const { pending, record } = makeRecorder(new Set(["real-ticket"]));
  await withServer(record, async (port) => {
    const response = await post(port, { ticket: "real-ticket" }, {});
    assert.equal(response.status, 200, "没有信号也不该是错误");
    assert.deepEqual(JSON.parse(response.body), { ok: true });
    assert.equal(pending.take("real-ticket"), null, "没有信号却记了一条观测");
  });
});

test("AC-042 编造的票号写不进任何东西——这是个无鉴权接口", async () => {
  const { pending, record } = makeRecorder(new Set(["real-ticket"]));
  await withServer(record, async (port) => {
    const response = await post(port, { ticket: "我编的票", timezone: "Asia/Tokyo" }, CF_HEADERS);
    // 对外仍然是 200：告诉攻击者「这张票不存在」等于送他一个枚举接口。
    assert.equal(response.status, 200);
    assert.equal(pending.take("我编的票"), null, "假票写进了暂存");
    assert.equal(pending.size, 0);
  });
});

test("AC-042 body 是垃圾也回 200，不把错误抛给加入页", async () => {
  const { record } = makeRecorder(new Set(["real-ticket"]));
  await withServer(record, async (port) => {
    for (const junk of ["这不是 JSON", "{", "null", "[]"]) {
      const response = await post(port, junk, CF_HEADERS);
      assert.equal(response.status, 200, `body=${junk} 时回了 ${response.status}`);
    }
  });
});

test("AC-042 采集侧抛错也不影响加入——handler 把异常吞掉", async () => {
  await withServer(() => { throw new Error("采集炸了"); }, async (port) => {
    const response = await post(port, { ticket: "real-ticket", timezone: "Asia/Tokyo" }, CF_HEADERS);
    assert.equal(response.status, 200, "采集出错让加入页看到了失败");
    assert.deepEqual(JSON.parse(response.body), { ok: true });
  });
});

test("这条路只收 POST——GET 不该能触发任何写入", async () => {
  const { record } = makeRecorder(new Set(["real-ticket"]));
  await withServer(record, async (port) => {
    const status = await new Promise((resolve) => {
      http.get({ host: "127.0.0.1", port, path: "/api/join/timezone" }, (response) => {
        response.resume();
        resolve(response.statusCode);
      }).on("error", () => resolve(0));
    });
    assert.notEqual(status, 200, `GET /api/join/timezone 回了 ${status}`);
  });
});
