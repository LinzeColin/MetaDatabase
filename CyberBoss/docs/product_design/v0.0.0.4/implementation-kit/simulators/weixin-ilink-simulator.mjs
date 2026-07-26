#!/usr/bin/env node
import http from "node:http";
import crypto from "node:crypto";

const host = process.env.SIM_WEIXIN_HOST || "127.0.0.1";
const requestedPort = Number(process.env.SIM_WEIXIN_PORT || 19080);
const token = process.env.SIM_WEIXIN_TOKEN || "sim-token-not-secret";
const accountId = "sim-ilink-bot";
const userId = "sim-authorized-user";
const deterministicEpochMs = 1_700_000_000_000;
const allowedFaults = new Set([
  "401",
  "403",
  "429",
  "500",
  "503",
  "timeout",
  "connection_reset",
  "unknown_outcome",
]);

if (!isLoopbackHost(host)) {
  console.error("WEIXIN_SIMULATOR=REFUSED reason=loopback_required");
  process.exit(64);
}
if (!Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
  console.error("WEIXIN_SIMULATOR=REFUSED reason=invalid_port");
  process.exit(64);
}

let sequence = 0;
let nextUpdateOrder = "ascending";
let qrStatus = "confirmed";
const messages = [];
const sent = [];
const receiptsByClientId = new Map();
const faults = {
  getupdates: [],
  sendmessage: [],
};

function isLoopbackHost(value) {
  return value === "127.0.0.1" || value === "::1" || value === "localhost";
}

function json(res, status, responseBody, headers = {}) {
  const text = `${JSON.stringify(responseBody)}\n`;
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(text),
    ...headers,
  });
  res.end(text);
}

function html(res, status, responseBody) {
  const text = String(responseBody);
  res.writeHead(status, {
    "content-type": "text/html; charset=utf-8",
    "content-length": Buffer.byteLength(text),
    "cache-control": "no-store",
  });
  res.end(text);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString("utf8");
  return text.trim() ? JSON.parse(text) : {};
}

function inbound(text, overrides = {}) {
  sequence += 1;
  return {
    seq: sequence,
    message_id: overrides.message_id || sequence,
    client_id: overrides.client_id || `sim-client-${sequence}`,
    from_user_id: overrides.from_user_id || userId,
    to_user_id: accountId,
    message_type: 1,
    message_state: 2,
    create_time_ms: overrides.create_time_ms || deterministicEpochMs + sequence,
    session_id: overrides.session_id || "sim-session",
    context_token: overrides.context_token || `sim-context-${sequence}`,
    item_list: [{ type: 1, text_item: { text: String(text) } }],
  };
}

function candidateCursor(batch, fallback) {
  return batch.reduce(
    (highest, item) => Math.max(highest, Number(item.seq) || 0),
    fallback,
  );
}

function providerReceiptId(clientId) {
  return `sim-receipt-${crypto.createHash("sha256").update(clientId).digest("hex").slice(0, 16)}`;
}

function recordSend(request, outcome = "confirmed") {
  const clientId = String(request?.msg?.client_id || `sim-send-${sent.length + 1}`);
  const existing = receiptsByClientId.get(clientId);
  if (existing) {
    return { ...existing, duplicate_ack: true };
  }
  const receipt = {
    client_id: clientId,
    provider_receipt_id: providerReceiptId(clientId),
    outcome,
    duplicate_ack: false,
  };
  receiptsByClientId.set(clientId, receipt);
  sent.push({
    sequence: sent.length + 1,
    client_id: clientId,
    provider_receipt_id: receipt.provider_receipt_id,
    outcome,
    body: request,
  });
  return receipt;
}

function takeFault(operation) {
  return faults[operation].shift() || "";
}

function applyTransportFault(req, res, fault, operation, request = {}) {
  if (!fault) {
    return { handled: false, receipt: null };
  }
  if (fault === "connection_reset") {
    req.socket.destroy();
    return { handled: true, receipt: null };
  }
  if (fault === "unknown_outcome" && operation === "sendmessage") {
    const receipt = recordSend(request, "unknown");
    req.socket.destroy();
    return { handled: true, receipt };
  }
  if (fault === "timeout") {
    json(
      res,
      504,
      { ret: 1, errcode: 50004, errmsg: `simulated ${operation} timeout` },
      { "x-cyberboss-simulated-transport-fault": "timeout" },
    );
    return { handled: true, receipt: null };
  }
  const status = Number(fault);
  const headers = status === 429 || status === 503 ? { "retry-after": "0" } : {};
  json(
    res,
    status,
    {
      ret: 1,
      errcode: status,
      errmsg: `injected ${operation} http ${status}`,
    },
    headers,
  );
  return { handled: true, receipt: null };
}

function normalizeFaultList(value, operation) {
  const list = Array.isArray(value) ? value : value ? [value] : [];
  return list.map((item) => String(item)).filter((item) => {
    if (!allowedFaults.has(item)) {
      return false;
    }
    return operation === "sendmessage" || item !== "unknown_outcome";
  });
}

function renderFixturePage() {
  const latestInbound = messages.at(-1);
  const latestOutbound = sent.at(-1);
  const inboundText = latestInbound?.item_list?.[0]?.text_item?.text || "ping";
  const outboundText =
    latestOutbound?.body?.msg?.item_list?.[0]?.text_item?.text || "pong";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CyberBoss WeChat Simulator Fixture</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; padding: 48px 24px; background: #07120e; color: #e8fff2; }
    main { width: 880px; margin: 0 auto; border: 1px solid #285c45; border-radius: 24px; padding: 34px; background: linear-gradient(145deg, #10251c, #081510); box-shadow: 0 28px 80px #0008; }
    .badge { display: inline-block; padding: 7px 12px; border-radius: 999px; background: #ffcc33; color: #2b2000; font-weight: 800; letter-spacing: .08em; }
    h1 { margin: 18px 0 8px; font-size: 34px; }
    .sub { color: #a8c8b7; margin-bottom: 28px; }
    .status { display: flex; gap: 10px; align-items: center; color: #83f0b4; font-weight: 700; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: #35e37f; box-shadow: 0 0 18px #35e37f; }
    .chat { margin-top: 30px; display: grid; gap: 18px; }
    .bubble { max-width: 70%; padding: 16px 20px; border-radius: 18px; font-size: 22px; line-height: 1.4; }
    .in { background: #21362d; border-bottom-left-radius: 5px; }
    .out { margin-left: auto; background: #21a45f; color: #04150c; border-bottom-right-radius: 5px; }
    footer { margin-top: 34px; padding-top: 18px; border-top: 1px solid #285c45; color: #8eaa9b; font-size: 14px; }
  </style>
</head>
<body>
  <main>
    <span class="badge">SIMULATOR FIXTURE — NOT REAL WECHAT</span>
    <h1>CyberBoss channel contract</h1>
    <p class="sub">Synthetic login and text round-trip evidence. No account, token, QR payload, or private chat is present.</p>
    <div class="status"><span class="dot"></span>QR state: CONFIRMED (fixture)</div>
    <section class="chat">
      <div class="bubble in">${escapeHtml(inboundText)}</div>
      <div class="bubble out">${escapeHtml(outboundText)}</div>
    </section>
    <footer>account=sim-ilink-bot · user=sim-authorized-user · claim_level=fixture</footer>
  </main>
</body>
</html>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const server = http.createServer(async (req, res) => {
  try {
    const address = server.address();
    const activePort = typeof address === "object" && address ? address.port : requestedPort;
    const url = new URL(req.url, `http://${host}:${activePort}`);

    if (req.method === "GET" && url.pathname === "/ilink/bot/get_bot_qrcode") {
      return json(res, 200, {
        qrcode: "sim-qrcode-not-real",
        qrcode_img_content: `http://${host}:${activePort}/admin/fixture`,
      });
    }
    if (req.method === "GET" && url.pathname === "/ilink/bot/get_qrcode_status") {
      return json(res, 200, {
        status: qrStatus,
        ...(qrStatus === "confirmed"
          ? {
              bot_token: token,
              ilink_bot_id: accountId,
              ilink_user_id: userId,
              baseurl: `http://${host}:${activePort}/`,
            }
          : {}),
      });
    }
    if (req.method === "POST" && url.pathname === "/ilink/bot/getupdates") {
      const request = await readBody(req);
      const faultResult = applyTransportFault(
        req,
        res,
        takeFault("getupdates"),
        "getupdates",
        request,
      );
      if (faultResult.handled) {
        return;
      }
      const cursor = Number.parseInt(String(request.get_updates_buf || "0"), 10) || 0;
      let batch = messages.filter((item) => Number(item.seq) > cursor);
      if (nextUpdateOrder === "reverse") {
        batch = [...batch].reverse();
        nextUpdateOrder = "ascending";
      }
      const next = candidateCursor(batch, cursor);
      return json(res, 200, {
        ret: 0,
        msgs: batch,
        get_updates_buf: String(next),
      });
    }
    if (req.method === "POST" && url.pathname === "/ilink/bot/sendmessage") {
      const request = await readBody(req);
      const faultResult = applyTransportFault(
        req,
        res,
        takeFault("sendmessage"),
        "sendmessage",
        request,
      );
      if (faultResult.handled) {
        return;
      }
      const receipt = recordSend(request);
      return json(res, 200, {
        ret: 0,
        errcode: 0,
        client_id: receipt.client_id,
        provider_receipt_id: receipt.provider_receipt_id,
        duplicate_ack: receipt.duplicate_ack,
      });
    }
    if (req.method === "POST" && url.pathname === "/ilink/bot/getconfig") {
      return json(res, 200, {
        ret: 0,
        errcode: 0,
        typing_ticket: "sim-typing-ticket",
      });
    }
    if (req.method === "POST" && url.pathname === "/ilink/bot/sendtyping") {
      return json(res, 200, { ret: 0, errcode: 0 });
    }
    if (req.method === "POST" && url.pathname === "/admin/inject") {
      const request = await readBody(req);
      const count = Math.max(1, Math.min(1000, Number(request.count || 1)));
      const created = [];
      for (let index = 0; index < count; index += 1) {
        const item = inbound(request.text || "simulated message", request);
        messages.push(item);
        created.push(item.message_id);
      }
      return json(res, 200, {
        injected: created.length,
        message_ids: created,
        cursor: String(sequence),
      });
    }
    if (req.method === "POST" && url.pathname === "/admin/replay") {
      const request = await readBody(req);
      const source = messages.find(
        (item) => String(item.message_id) === String(request.message_id),
      );
      if (!source) {
        return json(res, 404, { error: "message_not_found" });
      }
      messages.push({ ...source, seq: ++sequence });
      return json(res, 200, {
        replayed: source.message_id,
        cursor: String(sequence),
      });
    }
    if (req.method === "POST" && url.pathname === "/admin/order") {
      const request = await readBody(req);
      if (!["ascending", "reverse"].includes(request.next)) {
        return json(res, 400, { error: "invalid_order" });
      }
      nextUpdateOrder = request.next;
      return json(res, 200, { next_update_order: nextUpdateOrder });
    }
    if (req.method === "POST" && url.pathname === "/admin/qr-status") {
      const request = await readBody(req);
      if (!["wait", "scaned", "expired", "confirmed"].includes(request.status)) {
        return json(res, 400, { error: "invalid_qr_status" });
      }
      qrStatus = request.status;
      return json(res, 200, { status: qrStatus });
    }
    if (req.method === "POST" && url.pathname === "/admin/fault") {
      const request = await readBody(req);
      const invalid = [
        ...(Array.isArray(request.getupdates) ? request.getupdates : []),
        ...(Array.isArray(request.sendmessage) ? request.sendmessage : []),
      ].map(String).filter((item) => !allowedFaults.has(item));
      if (invalid.length) {
        return json(res, 400, { error: "invalid_fault", count: invalid.length });
      }
      faults.getupdates.push(...normalizeFaultList(request.getupdates, "getupdates"));
      faults.sendmessage.push(...normalizeFaultList(request.sendmessage, "sendmessage"));
      const legacyUpdateCount = Math.max(0, Number(request.update_failures || 0));
      const legacySendCount = Math.max(0, Number(request.send_failures || 0));
      faults.getupdates.push(...Array(legacyUpdateCount).fill("503"));
      faults.sendmessage.push(...Array(legacySendCount).fill("503"));
      return json(res, 200, {
        queued_getupdates_faults: faults.getupdates.length,
        queued_sendmessage_faults: faults.sendmessage.length,
      });
    }
    if (req.method === "POST" && url.pathname === "/admin/reset") {
      messages.length = 0;
      sent.length = 0;
      sequence = 0;
      qrStatus = "confirmed";
      nextUpdateOrder = "ascending";
      faults.getupdates.length = 0;
      faults.sendmessage.length = 0;
      receiptsByClientId.clear();
      return json(res, 200, { reset: true });
    }
    if (req.method === "GET" && url.pathname === "/admin/sent") {
      return json(res, 200, { sent });
    }
    if (req.method === "GET" && url.pathname === "/admin/state") {
      return json(res, 200, {
        sequence,
        queued_messages: messages.length,
        sent_messages: sent.length,
        unique_receipts: receiptsByClientId.size,
        queued_getupdates_faults: faults.getupdates.length,
        queued_sendmessage_faults: faults.sendmessage.length,
        next_update_order: nextUpdateOrder,
        qr_status: qrStatus,
      });
    }
    if (req.method === "GET" && url.pathname === "/admin/fixture") {
      return html(res, 200, renderFixturePage());
    }
    return json(res, 404, { error: "not_found", path: url.pathname });
  } catch (error) {
    return json(res, 500, { error: String(error?.message || error) });
  }
});

server.listen(requestedPort, host, () => {
  const address = server.address();
  const activePort = typeof address === "object" && address ? address.port : requestedPort;
  console.log(
    `WEIXIN_SIMULATOR=READY base_url=http://${host}:${activePort}/ user_id=${userId} claim_level=fixture`,
  );
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
