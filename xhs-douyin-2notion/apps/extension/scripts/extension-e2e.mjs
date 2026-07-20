import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";


const PROJECT_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const EXTENSION_ROOT = join(PROJECT_ROOT, "apps/extension");
const FIXTURE_PATH = join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/page_cases.json");
const EXPECTED_EXTENSION_ID = "chheapilbdfnpajmlkijppmblnlheeac";
const NATIVE_HOST = "com.linzecolin.x2n";
const INSTALL_CONFIRMATION = "INSTALL_X2N_NATIVE_HOST";
const UNINSTALL_CONFIRMATION = "UNINSTALL_X2N_NATIVE_HOST";

class E2EFailure extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

function requireCondition(condition, code) {
  if (!condition) throw new E2EFailure(code);
}

function runJson(args, env, label) {
  let output;
  try {
    output = execFileSync("uv", args, {
      cwd: PROJECT_ROOT,
      encoding: "utf8",
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch {
    throw new E2EFailure(`command_${label}`);
  }
  const lines = output.split(/\r?\n/u).filter((line) => line.startsWith("{"));
  requireCondition(lines.length === 1, `output_${label}`);
  return JSON.parse(lines[0]);
}

function uvPython(moduleName, ...args) {
  return [
    "run",
    "--quiet",
    "--isolated",
    "--frozen",
    "--package",
    "x2n-companion",
    "python",
    "-B",
    "-m",
    moduleName,
    ...args,
  ];
}

async function fileReceipt(path) {
  const bytes = await readFile(path);
  return {
    bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  };
}

function probeNativeLauncher(launcherPath, childEnv) {
  const request = Buffer.from(
    JSON.stringify({
      action: "get_capabilities",
      payload: {},
      payload_hash: "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      request_id: "00000000-0000-4000-8000-000000000004",
      schema_version: "1.0",
      sent_at: "2026-07-20T00:00:00Z",
    }),
  );
  const header = Buffer.alloc(4);
  header.writeUInt32LE(request.length, 0);
  let output;
  try {
    output = execFileSync(launcherPath, [`chrome-extension://${EXPECTED_EXTENSION_ID}/`], {
      encoding: null,
      env: childEnv,
      input: Buffer.concat([header, request]),
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch {
    throw new E2EFailure("native_launcher_probe");
  }
  requireCondition(output.length >= 4, "native_launcher_empty_response");
  const size = output.readUInt32LE(0);
  requireCondition(size === output.length - 4, "native_launcher_frame");
  const response = JSON.parse(output.subarray(4).toString("utf8"));
  requireCondition(response.accepted === true && response.status === "completed", "native_launcher_response");
}

async function submitSynthetic(worker) {
  return worker.evaluate(async ({ host }) => {
    const canonical = (value) => {
      if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
      if (Number.isSafeInteger(value)) return String(value);
      if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
      return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
    };
    const hash = async (value) => {
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value)));
      return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    };
    const payload = {
      auto_scroll: false,
      category_id: null,
      change_account_state: false,
      page_context: { content_id: "synthetic-e2e-001", content_type: "video", title: "Synthetic" },
      page_url: "https://www.xiaohongshu.com/explore/synthetic-e2e-001",
      platform: "xiaohongshu",
      relation: "saved_current",
      user_gesture: true,
    };
    const request = {
      action: "capture_current",
      payload,
      payload_hash: await hash(payload),
      request_id: crypto.randomUUID(),
      schema_version: "1.0",
      sent_at: new Date().toISOString(),
    };
    const first = await chrome.runtime.sendNativeMessage(host, request);
    const duplicate = await chrome.runtime.sendNativeMessage(host, request);
    return { duplicate, first };
  }, { host: NATIVE_HOST });
}

async function serviceWorkerTarget(cdp, extensionId) {
  const { targetInfos } = await cdp.send("Target.getTargets");
  return targetInfos.find(
    (target) => target.type === "service_worker" && target.url.startsWith(`chrome-extension://${extensionId}/`),
  );
}

async function lifecycleProbe(activeWorker) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const value = await activeWorker.evaluate(() => globalThis.__X2N_LIFECYCLE_PROBE);
      if (typeof value === "string" && value.length === 36) return value;
    } catch {
      // Playwright documents a short evaluate interruption at exact restart.
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new E2EFailure("service_worker_probe_unavailable");
}

let temporaryRoot;
let context;
let installed = false;
let env;
let currentStep = "bootstrap";

try {
  temporaryRoot = await mkdtemp(join(tmpdir(), "x2n-f004-e2e-"));
  const home = join(temporaryRoot, "home");
  const destination = join(temporaryRoot, "MediaCrawler");
  const dataRoot = join(destination, "xhs-douyin-2notion");
  const profile = join(temporaryRoot, "chromium-profile");
  const tracePath = join(temporaryRoot, "extension-trace.zip");
  const screenshotPath = join(temporaryRoot, "sidepanel.png");
  await mkdir(home, { mode: 0o700 });
  await mkdir(destination, { mode: 0o700 });
  await chmod(home, 0o700);
  await chmod(destination, 0o700);
  env = {
    HOME: home,
    LANG: "C.UTF-8",
    LC_ALL: "C.UTF-8",
    PATH: process.env.PATH ?? "",
    PYTHONPATH: "apps/companion/src:packages/contracts/src",
    PYTHONDONTWRITEBYTECODE: "1",
    UV_CACHE_DIR: join(temporaryRoot, "uv-cache"),
    UV_INDEX_URL: "https://pypi.org/simple",
    UV_KEYRING_PROVIDER: "disabled",
    UV_NO_CONFIG: "1",
    X2N_DATA_ROOT: dataRoot,
    X2N_DOWNLOAD_DESTINATION: destination,
  };
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) {
    env.PLAYWRIGHT_BROWSERS_PATH = process.env.PLAYWRIGHT_BROWSERS_PATH;
  }

  currentStep = "runtime_init";
  const initialized = runJson(uvPython("x2n_companion.runtime_cli", "init"), env, "runtime_init");
  requireCondition(initialized.status === "PASS" && initialized.schema_version === 2, "runtime_init_status");

  currentStep = "native_host_install";
  const hostInstall = runJson(
    uvPython(
      "x2n_companion.native_host_installer",
      "install",
      "--browser",
      "chromium",
      "--confirm",
      INSTALL_CONFIRMATION,
    ),
    env,
    "native_host_install",
  );
  requireCondition(hostInstall.status === "INSTALLED" && hostInstall.paths_emitted === false, "host_install_status");
  installed = true;

  // Playwright's isolated Chromium resolves per-user hosts from its explicit
  // user-data directory. Mirror only this test-owned manifest into that
  // temporary profile; the launcher and both manifests are removed in finally.
  const profileHostDirectory = join(profile, "NativeMessagingHosts");
  const installedManifest = join(
    home,
    "Library/Application Support/Chromium/NativeMessagingHosts",
    `${NATIVE_HOST}.json`,
  );
  await mkdir(profileHostDirectory, { recursive: true, mode: 0o700 });
  await writeFile(
    join(profileHostDirectory, `${NATIVE_HOST}.json`),
    await readFile(installedManifest),
    { mode: 0o600 },
  );
  const parsedManifest = JSON.parse(await readFile(installedManifest, "utf8"));
  probeNativeLauncher(parsedManifest.path, env);

  currentStep = "chromium_launch";
  const browserArgs = [
    `--disable-extensions-except=${EXTENSION_ROOT}`,
    `--load-extension=${EXTENSION_ROOT}`,
  ];
  if (process.env.X2N_E2E_BROWSER_LOG === "1") browserArgs.push("--enable-logging=stderr", "--v=1");
  context = await chromium.launchPersistentContext(profile, {
    args: browserArgs,
    channel: "chromium",
    env,
    headless: true,
  });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: false });

  currentStep = "service_worker_discovery";
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 15_000 });
  const extensionId = worker.url().split("/")[2];
  requireCondition(extensionId === EXPECTED_EXTENSION_ID, "extension_id_mismatch");

  currentStep = "sidepanel_ui";
  const page = await context.newPage();
  const consoleErrors = [];
  context.on("weberror", () => consoleErrors.push("weberror"));
  context.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push("console_error");
  });
  await page.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  currentStep = "direct_native_probe";
  const directProbe = await page.evaluate(async (host) => {
    const request = {
      action: "get_capabilities",
      payload: {},
      payload_hash: "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      request_id: "00000000-0000-4000-8000-000000000005",
      schema_version: "1.0",
      sent_at: "2026-07-20T00:00:00Z",
    };
    return Promise.race([
      chrome.runtime.sendNativeMessage(host, request)
        .then((response) => ({ response, state: "resolved" }))
        .catch(() => ({ state: "rejected" })),
      new Promise((resolve) => setTimeout(() => resolve({ state: "timeout" }), 10_000)),
    ]);
  }, NATIVE_HOST);
  requireCondition(directProbe.state === "resolved", `direct_native_${directProbe.state}`);
  requireCondition(directProbe.response?.accepted === true, "direct_native_response");
  currentStep = "worker_message_probe";
  const workerProbe = await page.evaluate(() =>
    Promise.race([
      chrome.runtime.sendMessage({ type: "X2N_HEALTH" })
        .then((response) => ({ response, state: "resolved" }))
        .catch(() => ({ state: "rejected" })),
      new Promise((resolve) => setTimeout(() => resolve({ state: "timeout" }), 10_000)),
    ]),
  );
  requireCondition(workerProbe.state === "resolved", `worker_message_${workerProbe.state}`);
  requireCondition(workerProbe.response?.ok === true, "worker_message_response");
  currentStep = "sidepanel_health";
  await page.locator("#tab-status").click();
  await page.locator("#refresh-status").waitFor({ state: "visible" });
  await page.locator("#refresh-status").click({ timeout: 10_000 });
  try {
    await page.locator("#host-status").filter({ hasText: "Local companion connected" }).waitFor({ timeout: 15_000 });
  } catch {
    const healthText = await page.locator("#host-status").textContent().catch(() => "");
    throw new E2EFailure(
      healthText?.includes("unavailable") ? "native_host_unavailable" : "sidepanel_health_timeout",
    );
  }
  currentStep = "sidepanel_ui";
  requireCondition(await page.locator("#panel-save button").isDisabled(), "unsupported_save_executable");

  const sections = ["save", "sync", "review", "status", "settings"];
  for (const section of sections) {
    await page.locator(`#tab-${section}`).click();
    requireCondition(await page.locator(`#panel-${section}`).isVisible(), `navigation_${section}`);
  }

  currentStep = "page_recognition";
  const fixture = JSON.parse(await readFile(FIXTURE_PATH, "utf8"));
  const recognition = await page.evaluate(async (cases) => {
    const { recognizePage } = await import(chrome.runtime.getURL("src/page-support.js"));
    return cases.map((item) => ({ id: item.id, result: recognizePage(item.url) }));
  }, fixture.cases);
  const fixtureFailures = recognition.filter(({ id, result }) => {
    const expected = fixture.cases.find((item) => item.id === id);
    return result.supported !== expected.supported || result.platform !== expected.platform || result.executable !== false;
  });
  requireCondition(fixtureFailures.length === 0, "fixture_recognition");

  currentStep = "native_submission";
  const submission = await submitSynthetic(worker);
  requireCondition(submission.first?.accepted === true && submission.first?.status === "queued", "submission_rejected");
  requireCondition(submission.duplicate?.job_id === submission.first.job_id, "duplicate_job_created");
  const jobId = submission.first.job_id;

  currentStep = "restart_chaos";
  const cdp = await context.newCDPSession(page);
  let lostJobs = 0;
  let wrongStatuses = 0;
  let restarts = 0;
  for (let index = 0; index < 100; index += 1) {
    const lifecycleBefore = await lifecycleProbe(worker);
    const target = await serviceWorkerTarget(cdp, extensionId);
    requireCondition(Boolean(target), "service_worker_target_missing");
    const closed = await cdp.send("Target.closeTarget", { targetId: target.targetId });
    requireCondition(closed.success === true, "service_worker_close_failed");
    const state = await page.evaluate(
      (value) => chrome.runtime.sendMessage({ jobId: value, type: "X2N_GET_JOB" }),
      jobId,
    );
    if (!state?.ok || state.response?.job_id !== jobId) lostJobs += 1;
    if (state?.response?.status !== "queued") wrongStatuses += 1;
    const availableWorkers = context.serviceWorkers().filter((item) => item.url().startsWith(`chrome-extension://${extensionId}/`));
    if (availableWorkers.length > 0) worker = availableWorkers[0];
    const lifecycleAfter = await lifecycleProbe(worker);
    requireCondition(lifecycleAfter !== lifecycleBefore, "service_worker_not_restarted");
    restarts += 1;
  }

  currentStep = "database_reconciliation";
  const health = runJson(uvPython("x2n_companion.runtime_cli", "health"), env, "runtime_health");
  requireCondition(health.table_counts?.request_ledger === 1, "request_ledger_count");
  requireCondition(health.table_counts?.run_record === 1, "run_record_count");
  requireCondition(lostJobs === 0 && wrongStatuses === 0, "chaos_reconciliation");

  currentStep = "evidence_receipts";
  await page.locator("#tab-status").click();
  await page.screenshot({ path: screenshotPath });
  await context.tracing.stop({ path: tracePath });
  const screenshot = await fileReceipt(screenshotPath);
  const trace = await fileReceipt(tracePath);
  requireCondition(consoleErrors.length === 0, "console_errors");

  const result = {
    console_uncaught_errors: consoleErrors.length,
    duplicate_jobs: health.table_counts.run_record - 1,
    extension_id_match: true,
    fixture_cases: fixture.cases.length,
    fixture_recognition_passed: fixture.cases.length - fixtureFailures.length,
    lost_jobs: lostJobs,
    owner_canary: "NOT_RUN",
    platform_calls: 0,
    real_accounts: 0,
    request_ledger_rows: health.table_counts.request_ledger,
    screenshot,
    service_worker_restarts: restarts,
    status: "PASS",
    trace,
    wrong_statuses: wrongStatuses,
  };
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  const code = error instanceof E2EFailure ? error.code : `unexpected_${currentStep}`;
  process.stderr.write(`${JSON.stringify({ code, status: "FAIL_CLOSED" })}\n`);
  process.exitCode = 1;
} finally {
  if (context) await context.close().catch(() => undefined);
  if (installed && env) {
    try {
      runJson(
        uvPython(
          "x2n_companion.native_host_installer",
          "uninstall",
          "--browser",
          "chromium",
          "--confirm",
          UNINSTALL_CONFIRMATION,
        ),
        env,
        "native_host_uninstall",
      );
    } catch {
      process.exitCode = 1;
    }
  }
  if (temporaryRoot) await rm(temporaryRoot, { recursive: true, force: true });
}
