import { chromium } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const baseURL = (process.env.PWB_BASE_URL || "https://mydairy.linzezhang.com").replace(/\/$/, "");
const mailBase = "https://api.mail.tm";
const outputDir = process.env.PWB_AUDIT_OUTPUT || "/tmp/pwb-ephemeral-audit";
const coolifyBase = (process.env.COOLIFY_BASE_URL || "").replace(/\/$/, "");
const coolifyToken = (process.env.COOLIFY_API_TOKEN || "").replace(/^Bearer\s+/i, "");
const runId = `${Date.now()}-${crypto.randomBytes(4).toString("hex")}`;
const report = {
  runId,
  baseURL,
  mailboxProvisioning: "NOT_RUN",
  accountA: {},
  accountB: {},
  preRedeploy: {},
  deployment: {},
  postRedeploy: {},
  cleanup: {},
  overall: "NOT_PASS",
};

await fs.mkdir(outputDir, { recursive: true });

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function safeError(error) {
  const text = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  return text
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[email-redacted]")
    .replace(/([?&](?:token|state|code)=)[^&\s]+/gi, "$1[redacted]")
    .slice(0, 2000);
}

async function writeReport() {
  await fs.writeFile(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2), "utf8");
}

async function fetchJson(url, options = {}, expected = [200]) {
  const response = await fetch(url, options);
  const text = await response.text();
  let value = null;
  if (text) {
    try {
      value = JSON.parse(text);
    } catch {
      value = { raw: text.slice(0, 500) };
    }
  }
  if (!expected.includes(response.status)) {
    throw new Error(`HTTP ${response.status} from ${new URL(url).pathname}: ${JSON.stringify(value).slice(0, 500)}`);
  }
  return { response, value };
}

async function createMailbox(label) {
  const { value: domains } = await fetchJson(`${mailBase}/domains`);
  const members = domains?.["hydra:member"] || domains?.member || [];
  const active = members.find((item) => item?.isActive && !item?.isPrivate) || members.find((item) => item?.isActive);
  if (!active?.domain) throw new Error("Mail.tm has no active domain");
  const local = `pwb-${label}-${runId}`.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 48);
  const address = `${local}@${active.domain}`;
  const password = `Pwb!${crypto.randomBytes(18).toString("base64url")}9a`;
  const { value: account } = await fetchJson(`${mailBase}/accounts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ address, password }),
  }, [201]);
  const { value: token } = await fetchJson(`${mailBase}/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ address, password }),
  }, [200]);
  if (!account?.id || !token?.token) throw new Error("Mail.tm account/token response incomplete");
  return { id: account.id, address, password, token: token.token };
}

async function deleteMailbox(mailbox) {
  if (!mailbox?.id || !mailbox?.token) return false;
  try {
    const response = await fetch(`${mailBase}/accounts/${encodeURIComponent(mailbox.id)}`, {
      method: "DELETE",
      headers: { authorization: `Bearer ${mailbox.token}` },
    });
    return response.status === 204 || response.status === 404;
  } catch {
    return false;
  }
}

function extractVerificationUrl(detail) {
  const candidates = [];
  if (Array.isArray(detail?.verifications)) candidates.push(...detail.verifications);
  if (typeof detail?.text === "string") candidates.push(detail.text);
  if (Array.isArray(detail?.html)) candidates.push(...detail.html);
  else if (typeof detail?.html === "string") candidates.push(detail.html);
  const links = [];
  for (const candidate of candidates) {
    if (typeof candidate !== "string") continue;
    if (/^https?:\/\//i.test(candidate.trim())) links.push(candidate.trim());
    links.push(...(candidate.match(/https?:\/\/[^\s"'<>]+/g) || []));
  }
  const host = new URL(baseURL).hostname;
  for (const raw of links) {
    const normalized = raw.replaceAll("&amp;", "&").replace(/[),.;]+$/, "");
    try {
      const url = new URL(normalized);
      if (url.hostname === host && /verify-email/i.test(url.pathname + url.search)) return url.toString();
    } catch {
      // Ignore malformed candidates.
    }
  }
  return null;
}

async function waitForVerification(mailbox, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { value: list } = await fetchJson(`${mailBase}/messages`, {
      headers: { authorization: `Bearer ${mailbox.token}` },
    });
    const messages = list?.["hydra:member"] || list?.member || [];
    for (const message of messages) {
      if (!message?.id) continue;
      const { value: detail } = await fetchJson(`${mailBase}/messages/${encodeURIComponent(message.id)}`, {
        headers: { authorization: `Bearer ${mailbox.token}` },
      });
      const verification = extractVerificationUrl(detail);
      if (verification) return verification;
    }
    await sleep(3000);
  }
  throw new Error("Verification email did not arrive within the bounded window");
}

async function waitForTurnstile(page, label) {
  try {
    await page.waitForFunction(() => {
      const responses = Array.from(document.querySelectorAll('input[name="cf-turnstile-response"]'));
      return responses.some((input) => typeof input.value === "string" && input.value.trim().length > 20);
    }, undefined, { timeout: 90_000 });
  } catch {
    const message = await page.locator(".auth-captcha-message").last().textContent().catch(() => "");
    throw new Error(`${label} Turnstile did not produce a token${message ? `: ${message.trim()}` : ""}`);
  }
}

async function signUpAndVerify(browser, label, mailbox) {
  const context = await browser.newContext({ locale: "zh-CN", timezoneId: "Australia/Sydney" });
  const page = await context.newPage();
  await page.goto(`${baseURL}/auth/sign-up`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("名字").fill(`PWB Audit ${label}`);
  await page.getByLabel("邮箱").fill(mailbox.address);
  await page.getByLabel("密码").fill(mailbox.password);
  await waitForTurnstile(page, `${label} sign-up`);
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes("/api/auth/sign-up/email") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "注册", exact: true }).click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`${label} sign-up returned HTTP ${response.status()}`);
  await page.waitForURL(/\/auth\/verify-email/, { timeout: 30_000 });
  const verificationUrl = await waitForVerification(mailbox);
  await page.goto(verificationUrl, { waitUntil: "domcontentloaded" });
  await page.waitForURL(/\/auth\/sign-in|view=home/, { timeout: 45_000 });
  await context.close();
  return true;
}

async function signIn(browser, label, mailbox) {
  const context = await browser.newContext({ locale: "zh-CN", timezoneId: "Australia/Sydney" });
  const page = await context.newPage();
  await page.goto(`${baseURL}/auth/sign-in`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("邮箱").fill(mailbox.address);
  await page.getByLabel("密码").fill(mailbox.password);
  await waitForTurnstile(page, `${label} sign-in`);
  const responsePromise = page.waitForResponse((response) =>
    response.url().includes("/api/auth/sign-in/email") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`${label} sign-in returned HTTP ${response.status()}`);
  await page.waitForURL(/view=home/, { timeout: 45_000 });
  return context;
}

function mutationUrl(url) {
  return `${url}${url.includes("?") ? "&" : "?"}request_id=${encodeURIComponent(crypto.randomUUID())}`;
}

async function apiJson(context, method, url, data) {
  const requestUrl = method === "GET" ? url : mutationUrl(url);
  const options = {
    headers: {
      ...(method === "GET" ? {} : { origin: baseURL }),
      ...(data === undefined ? {} : { "content-type": "application/json" }),
    },
    ...(data === undefined ? {} : { data }),
  };
  const response = await context.request[method.toLowerCase()](requestUrl, options);
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text.slice(0, 300) }; }
  if (!response.ok()) throw new Error(`${method} ${url} returned ${response.status()}: ${JSON.stringify(body).slice(0, 500)}`);
  return body;
}

async function listIds(context, resource) {
  const body = await apiJson(context, "GET", `${baseURL}/api/mydairy/${resource}`);
  return new Set((body?.data || []).map((row) => row?.id).filter(Boolean));
}

async function createResource(context, resource, payload) {
  const body = await apiJson(context, "POST", `${baseURL}/api/mydairy/${resource}`, payload);
  const id = body?.data?.id;
  if (!id) throw new Error(`POST ${resource} did not return an id`);
  return id;
}

async function deleteResource(context, resource, id) {
  await apiJson(context, "DELETE", `${baseURL}/api/mydairy/${resource}/${encodeURIComponent(id)}`);
}

async function uploadImage(context) {
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=",
    "base64",
  );
  const response = await context.request.post(mutationUrl(`${baseURL}/api/mydairy/files`), {
    headers: { origin: baseURL },
    multipart: {
      module: "diary",
      file: { name: "pwb-audit.png", mimeType: "image/png", buffer: png },
    },
  });
  const text = await response.text();
  let body = null;
  try { body = JSON.parse(text); } catch { body = { raw: text.slice(0, 300) }; }
  if (!response.ok() || !body?.data?.id) {
    throw new Error(`File upload returned ${response.status()}: ${JSON.stringify(body).slice(0, 500)}`);
  }
  return body.data.id;
}

async function verifyFileBoundary(contextA, contextB, fileId) {
  const a = await contextA.request.get(`${baseURL}/api/mydairy/files/${encodeURIComponent(fileId)}`);
  if (!a.ok()) throw new Error(`Account A could not read its file: HTTP ${a.status()}`);
  const b = await contextB.request.get(`${baseURL}/api/mydairy/files/${encodeURIComponent(fileId)}`);
  if (![403, 404].includes(b.status())) throw new Error(`Account B file boundary returned HTTP ${b.status()}`);
}

async function deleteFile(context, fileId) {
  const response = await context.request.delete(mutationUrl(`${baseURL}/api/mydairy/files/${encodeURIComponent(fileId)}`), {
    headers: { origin: baseURL },
  });
  if (!response.ok()) throw new Error(`File delete returned HTTP ${response.status()}`);
}

async function deleteProductAccount(context) {
  const requested = await apiJson(context, "POST", `${baseURL}/api/account/delete`, { action: "request" });
  const token = requested?.recoveryToken;
  if (!token) throw new Error("Account deletion request did not return a recovery token");
  await apiJson(context, "POST", `${baseURL}/api/account/delete`, { action: "confirm", recoveryToken: token });
  return true;
}

async function discoverCoolifyApplication() {
  if (!coolifyBase || !coolifyToken) throw new Error("Coolify audit credentials are missing");
  const apiRoot = `${coolifyBase.replace(/\/api\/v1$/, "")}/api/v1`;
  const headerCandidates = [
    { authorization: `Bearer ${coolifyToken}` },
    { "x-api-key": coolifyToken },
    { "x-coolify-token": coolifyToken },
  ];
  let rows = null;
  let selectedHeaders = null;
  for (const headers of headerCandidates) {
    const response = await fetch(`${apiRoot}/applications`, { headers });
    if (response.ok) {
      rows = await response.json();
      selectedHeaders = headers;
      break;
    }
  }
  if (!selectedHeaders) throw new Error("Coolify rejected every supported token header");
  const list = Array.isArray(rows) ? rows : rows?.applications || rows?.data || [];
  const matches = list.filter((row) => {
    const text = [row?.name, row?.fqdn, row?.git_repository, row?.base_directory, row?.dockerfile_location]
      .map((value) => String(value || "").toLowerCase()).join(" ");
    return text.includes("personal-workbench") || text.includes("mydairy") || text.includes("personal workbench");
  });
  const uuids = [...new Set(matches.map((row) => row?.uuid).filter(Boolean))];
  if (uuids.length !== 1) throw new Error(`Expected one Coolify app, found ${uuids.length}`);
  return { apiRoot, headers: selectedHeaders, uuid: uuids[0] };
}

async function redeployCurrentMain() {
  const app = await discoverCoolifyApplication();
  const response = await fetch(`${app.apiRoot}/deploy?uuid=${encodeURIComponent(app.uuid)}&force=false`, {
    method: "POST",
    headers: app.headers,
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Coolify deployment request returned HTTP ${response.status()}`);
  const deploymentUuid = value?.deployment_uuid || value?.uuid || value?.deployments?.[0]?.deployment_uuid;
  if (!deploymentUuid) throw new Error("Coolify did not return a deployment UUID");
  const deadline = Date.now() + 15 * 60_000;
  let lastStatus = "unknown";
  while (Date.now() < deadline) {
    await sleep(10_000);
    const statusResponse = await fetch(`${app.apiRoot}/deployments/${encodeURIComponent(deploymentUuid)}`, {
      headers: app.headers,
    });
    if (!statusResponse.ok) continue;
    const statusBody = await statusResponse.json().catch(() => ({}));
    lastStatus = String(statusBody?.status || "unknown").toLowerCase();
    if (["finished", "success"].includes(lastStatus)) break;
    if (["failed", "cancelled", "canceled"].includes(lastStatus)) {
      throw new Error(`Coolify deployment ended with ${lastStatus}`);
    }
  }
  if (!["finished", "success"].includes(lastStatus)) throw new Error(`Coolify deployment timed out at ${lastStatus}`);
  const healthDeadline = Date.now() + 3 * 60_000;
  while (Date.now() < healthDeadline) {
    try {
      const health = await fetch(`${baseURL}/api/health`, { cache: "no-store" });
      const body = await health.json().catch(() => ({}));
      if (health.ok && body?.ready === true) return { status: lastStatus, health: "ready" };
    } catch {
      // Keep waiting during container replacement.
    }
    await sleep(3000);
  }
  throw new Error("Public health did not recover after deployment");
}

let browser;
let mailboxA;
let mailboxB;
let contextA;
let contextB;
let fileId;
const created = [];
let markerTodoId;

try {
  mailboxA = await createMailbox("a");
  mailboxB = await createMailbox("b");
  report.mailboxProvisioning = "PASS";
  await writeReport();

  browser = await chromium.launch({ headless: true });
  await signUpAndVerify(browser, "A", mailboxA);
  report.accountA.signUpAndVerify = "PASS";
  await signUpAndVerify(browser, "B", mailboxB);
  report.accountB.signUpAndVerify = "PASS";

  contextA = await signIn(browser, "A", mailboxA);
  contextB = await signIn(browser, "B", mailboxB);
  report.accountA.signIn = "PASS";
  report.accountB.signIn = "PASS";

  const today = new Date().toISOString().slice(0, 10);
  const now = Date.now();
  const futureDate = `2099-${String((now % 12) + 1).padStart(2, "0")}-${String((now % 27) + 1).padStart(2, "0")}`;

  const habitId = await createResource(contextA, "habits", { title: `审计习惯-${runId}`, iconKey: "habit_read.png", sortOrder: 1, active: true });
  created.push(["habits", habitId]);
  const checkinId = await createResource(contextA, "habit-checkins", { habitId, localDate: futureDate });
  created.push(["habit-checkins", checkinId]);
  markerTodoId = await createResource(contextA, "todos", { title: `PWB-CLOUD-${runId}`, note: "cloud persistence audit", dueDate: today, priority: "normal", completed: false, completedAt: null });
  created.push(["todos", markerTodoId]);
  for (const [resource, payload] of [
    ["ledger", { kind: "expense", amountCents: 123, currency: "CNY", localDate: today, category: "验收", note: "" }],
    ["food", { foodName: "验收食物", calories: 10, meal: "breakfast", localDate: today, note: "", photoObjectId: null, source: "manual" }],
    ["exercise", { activity: "验收运动", durationMinutes: 10, caloriesBurned: 1, localDate: today, note: "" }],
    ["weights", { weightGrams: 60000, localDate: futureDate, note: "" }],
    ["schedule", { title: "验收日程", note: "", startsAt: now, endsAt: now + 3600000, allDay: false }],
    ["anniversaries", { title: "验收纪念", localDate: today, repeatYearly: true, note: "" }],
    ["diary", { localDate: today, mood: "好", title: "验收日记", body: "实际云环境事务", photoObjectId: null }],
  ]) {
    const id = await createResource(contextA, resource, payload);
    created.push([resource, id]);
  }
  const goalId = await createResource(contextA, "savings-goals", { title: "验收存钱", targetCents: 10000, currency: "CNY", targetDate: today, archived: false });
  created.push(["savings-goals", goalId]);
  const transactionId = await createResource(contextA, "savings-transactions", { goalId, amountCents: 100, localDate: today, note: "" });
  created.push(["savings-transactions", transactionId]);
  const periodId = await createResource(contextA, "periods", { startDate: futureDate, endDate: futureDate, note: "" });
  created.push(["periods", periodId]);

  for (const [resource, id] of created) {
    const idsA = await listIds(contextA, resource);
    const idsB = await listIds(contextB, resource);
    if (!idsA.has(id)) throw new Error(`Account A cannot read created ${resource}`);
    if (idsB.has(id)) throw new Error(`Account B can read Account A ${resource}`);
  }
  report.preRedeploy.allResourceWritesAndIsolation = "PASS";

  fileId = await uploadImage(contextA);
  await verifyFileBoundary(contextA, contextB, fileId);
  report.preRedeploy.objectStorageAndIsolation = "PASS";

  await contextA.close();
  contextA = null;
  const secondDeviceA = await signIn(browser, "A-second-device", mailboxA);
  const beforeIds = await listIds(secondDeviceA, "todos");
  if (!beforeIds.has(markerTodoId)) throw new Error("Second-device login cannot read the cloud todo before redeploy");
  await secondDeviceA.close();
  report.preRedeploy.secondDeviceRead = "PASS";
  await writeReport();

  report.deployment = await redeployCurrentMain();

  contextA = await signIn(browser, "A-after-redeploy", mailboxA);
  const afterIdsA = await listIds(contextA, "todos");
  if (!afterIdsA.has(markerTodoId)) throw new Error("Cloud todo disappeared after current-main redeploy");
  contextB = contextB || await signIn(browser, "B-after-redeploy", mailboxB);
  const afterIdsB = await listIds(contextB, "todos");
  if (afterIdsB.has(markerTodoId)) throw new Error("Account B can read Account A todo after redeploy");
  if (fileId) await verifyFileBoundary(contextA, contextB, fileId);
  report.postRedeploy.databasePersistence = "PASS";
  report.postRedeploy.accountIsolation = "PASS";
  report.postRedeploy.objectPersistenceAndIsolation = fileId ? "PASS" : "NOT_RUN";

  if (fileId) {
    await deleteFile(contextA, fileId);
    fileId = null;
  }
  for (const [resource, id] of [...created].reverse()) await deleteResource(contextA, resource, id);
  created.length = 0;
  report.cleanup.recordsAndObject = "PASS";

  await deleteProductAccount(contextA);
  contextA = null;
  await deleteProductAccount(contextB);
  contextB = null;
  report.cleanup.productAccounts = "PASS";

  report.cleanup.mailboxes = (await deleteMailbox(mailboxA)) && (await deleteMailbox(mailboxB)) ? "PASS" : "PARTIAL";
  mailboxA = null;
  mailboxB = null;
  report.overall = "PASS";
} catch (error) {
  report.error = safeError(error);
  report.overall = "NOT_PASS";
} finally {
  try { if (fileId && contextA) await deleteFile(contextA, fileId); } catch {}
  if (contextA) {
    for (const [resource, id] of [...created].reverse()) {
      try { await deleteResource(contextA, resource, id); } catch {}
    }
    try { await deleteProductAccount(contextA); } catch {}
    try { await contextA.close(); } catch {}
  }
  if (contextB) {
    try { await deleteProductAccount(contextB); } catch {}
    try { await contextB.close(); } catch {}
  }
  if (mailboxA) await deleteMailbox(mailboxA);
  if (mailboxB) await deleteMailbox(mailboxB);
  if (browser) await browser.close().catch(() => undefined);
  await writeReport();
}

console.log(JSON.stringify({ overall: report.overall, report: path.join(outputDir, "report.json") }));
process.exit(report.overall === "PASS" ? 0 : 1);
