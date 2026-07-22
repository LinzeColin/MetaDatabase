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
const REQUESTED_PLATFORM = process.argv[2] ?? "xiaohongshu";
const CURRENT_PAGE_CONFIGS = Object.freeze({
  bilibili: Object.freeze({
    caseId: "bilibili-video-detail",
    expectedPath: "/video/synthetic-bili-video-001",
    expectedUrlFragment: "bilibili.com/video/",
    fixtureRoot: join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/bilibili_current_page"),
    metricPrefix: "bilibili",
  }),
  douyin: Object.freeze({
    caseId: "douyin-video-detail",
    expectedPath: "/video/synthetic-video-001",
    expectedUrlFragment: "douyin.com/video/",
    fixtureRoot: join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/douyin_current_page"),
    metricPrefix: "douyin",
  }),
  xiaohongshu: Object.freeze({
    caseId: "xhs-image-detail",
    expectedPath: "/explore/synthetic-note-image-001",
    expectedUrlFragment: "xiaohongshu.com/explore/",
    fixtureRoot: join(PROJECT_ROOT, "packages/test-fixtures/extension/v1/xhs_current_page"),
    metricPrefix: "xhs",
  }),
});
const CURRENT_PAGE_CONFIG = CURRENT_PAGE_CONFIGS[REQUESTED_PLATFORM];
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
  requireCondition(Boolean(CURRENT_PAGE_CONFIG), "unsupported_e2e_platform");
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
    "--enable-unsafe-extension-debugging",
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
    const expectedExecutable = expected.supported && expected.platform === "xiaohongshu";
    return result.supported !== expected.supported
      || result.platform !== expected.platform
      || result.executable !== expectedExecutable;
  });
  requireCondition(fixtureFailures.length === 0, "fixture_recognition");

  currentStep = `${CURRENT_PAGE_CONFIG.metricPrefix}_active_tab_grant`;
  const currentPageFixture = JSON.parse(
    await readFile(join(CURRENT_PAGE_CONFIG.fixtureRoot, "fixture_manifest.json"), "utf8"),
  );
  const captureCase = currentPageFixture.cases.find((item) => item.id === CURRENT_PAGE_CONFIG.caseId);
  requireCondition(Boolean(captureCase), `${CURRENT_PAGE_CONFIG.metricPrefix}_fixture_missing`);
  const captureHtml = await readFile(join(CURRENT_PAGE_CONFIG.fixtureRoot, captureCase.file), "utf8");
  const routedUrl = new URL(captureCase.page_url);
  routedUrl.hash = "";
  const capturePage = await context.newPage();
  let blockedPlatformNetworkRequests = 0;
  let fixtureDocumentsFulfilled = 0;
  let platformRequestsObserved = 0;
  let platformCalls = 0;
  await capturePage.route("**/*", (route) => {
    const requestUrl = new URL(route.request().url());
    requestUrl.hash = "";
    const platformRequest = requestUrl.hostname.toLowerCase() === routedUrl.hostname.toLowerCase();
    if (platformRequest) platformRequestsObserved += 1;
    if (
      requestUrl.href === routedUrl.href
      && route.request().isNavigationRequest()
      && route.request().resourceType() === "document"
    ) {
      fixtureDocumentsFulfilled += 1;
      return route.fulfill({
        body: captureHtml,
        contentType: "text/html; charset=utf-8",
        status: 200,
      });
    }
    if (platformRequest) blockedPlatformNetworkRequests += 1;
    return route.abort("blockedbyclient");
  });
  await capturePage.goto(captureCase.page_url, { waitUntil: "domcontentloaded" });
  platformCalls = platformRequestsObserved - fixtureDocumentsFulfilled - blockedPlatformNetworkRequests;
  requireCondition(fixtureDocumentsFulfilled === 1, `${CURRENT_PAGE_CONFIG.metricPrefix}_fixture_document_count`);
  requireCondition(platformCalls === 0, `${CURRENT_PAGE_CONFIG.metricPrefix}_platform_network_call`);
  await capturePage.bringToFront();
  const beforeAction = await page.evaluate(async () => {
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find((candidate) => candidate.active === true);
    let injection = "rejected";
    if (Number.isSafeInteger(tab?.id)) {
      try {
        await chrome.scripting.executeScript({
          func: () => globalThis.location.pathname,
          target: { tabId: tab.id },
          world: "ISOLATED",
        });
        injection = "resolved";
      } catch {
        injection = "rejected";
      }
    }
    const capture = Number.isSafeInteger(tab?.id)
      ? await chrome.runtime.sendMessage({ tabId: tab.id, type: "X2N_CAPTURE_CURRENT" })
      : { ok: false, status: "test_tab_unavailable" };
    return { capture, injection };
  });
  requireCondition(
    beforeAction.injection === "rejected",
    `${CURRENT_PAGE_CONFIG.metricPrefix}_pre_action_injection_allowed`,
  );
  requireCondition(
    beforeAction.capture?.ok === false && beforeAction.capture?.code === "X2N_POLICY_BLOCKED",
    `${CURRENT_PAGE_CONFIG.metricPrefix}_pre_action_capture_allowed`,
  );
  const browser = context.browser();
  requireCondition(Boolean(browser), "browser_cdp_unavailable");
  try {
    const actionCdp = await browser.newBrowserCDPSession();
    const { targetInfos } = await actionCdp.send("Target.getTargets", {
      filter: [{ exclude: false, type: "tab" }],
    });
    const captureTarget = targetInfos.find(
      (target) => target.type === "tab" && target.url.startsWith(routedUrl.href),
    );
    requireCondition(Boolean(captureTarget), "cdp_target_info_unavailable");
    await actionCdp.send("Extensions.triggerAction", {
      id: extensionId,
      targetId: captureTarget.targetId,
    });
    await actionCdp.detach();
  } catch (error) {
    if (error instanceof E2EFailure) throw error;
    const diagnostic = String(error?.message ?? error);
    if (process.env.X2N_E2E_DEBUG === "1") {
      const safeDiagnostic = diagnostic
        .replace(/\/(?:Users|home)\/[^/\s]+\//gu, "<local-root>/")
        .replace(/[0-9a-f]{32,}/giu, "<opaque-id>");
      process.stderr.write(`CDP_DIAGNOSTIC=${safeDiagnostic.slice(0, 400)}\n`);
    }
    if (diagnostic.includes("wasn't found")) throw new E2EFailure("cdp_trigger_action_method_missing");
    if (/unsafe|remote-debugging-pipe/iu.test(diagnostic)) throw new E2EFailure("cdp_trigger_action_flag_missing");
    if (/target/iu.test(diagnostic)) throw new E2EFailure("cdp_trigger_action_target_missing");
    if (/newBrowserCDPSession/iu.test(diagnostic)) throw new E2EFailure("browser_cdp_method_missing");
    throw new E2EFailure("cdp_trigger_action_failed");
  }
  const activeTabProbe = await page.evaluate(async (expected) => {
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find((candidate) => candidate.active === true);
    let injection = false;
    let injectedExpectedPage = false;
    if (Number.isSafeInteger(tab?.id)) {
      try {
        const result = await chrome.scripting.executeScript({
          func: () => ({ path: globalThis.location.pathname, protocol: globalThis.location.protocol }),
          target: { tabId: tab.id },
          world: "ISOLATED",
        });
        injection = result.length === 1 && result[0]?.result?.protocol === "https:";
        injectedExpectedPage = result[0]?.result?.path === expected.path;
      } catch {
        injection = false;
      }
    }
    return {
      has_expected_url: typeof tab?.url === "string" && tab.url.includes(expected.urlFragment),
      injection,
      injected_expected_page: injectedExpectedPage,
      is_active: tab?.active === true,
      tab_available: Number.isSafeInteger(tab?.id),
    };
  }, { path: CURRENT_PAGE_CONFIG.expectedPath, urlFragment: CURRENT_PAGE_CONFIG.expectedUrlFragment });
  requireCondition(activeTabProbe.tab_available, `${CURRENT_PAGE_CONFIG.metricPrefix}_active_tab_missing`);
  requireCondition(activeTabProbe.injection, `${CURRENT_PAGE_CONFIG.metricPrefix}_active_tab_not_granted`);
  requireCondition(activeTabProbe.injected_expected_page, `${CURRENT_PAGE_CONFIG.metricPrefix}_active_page_mismatch`);
  requireCondition(activeTabProbe.has_expected_url, `${CURRENT_PAGE_CONFIG.metricPrefix}_active_url_unavailable`);
  requireCondition(activeTabProbe.is_active, `${CURRENT_PAGE_CONFIG.metricPrefix}_target_not_active`);
  // Headless Chromium does not expose the opened side panel as a Playwright
  // Page target. Reload the test-owned Side Panel document in the background
  // so its real initialization path observes the action-granted active tab.
  await page.reload({ waitUntil: "domcontentloaded" });
  if (process.env.X2N_E2E_DEBUG === "1") {
    const pageUrls = context.pages().map((item) => item.url().replace(/[?#].*$/u, ""));
    process.stderr.write(`E2E_PAGES=${JSON.stringify(pageUrls)}\n`);
    const sidePanelProbe = await page.evaluate(async () => {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      const { recognizePage } = await import(chrome.runtime.getURL("src/page-support.js"));
      return {
        buttonDisabled: document.querySelector("#save-current")?.disabled,
        pageStatus: document.querySelector("#page-status")?.textContent,
        support: recognizePage(tab?.url ?? ""),
        tabActive: tab?.active,
      };
    });
    process.stderr.write(`E2E_SIDEPANEL=${JSON.stringify(sidePanelProbe)}\n`);
  }

  currentStep = `${CURRENT_PAGE_CONFIG.metricPrefix}_current_page_submission`;
  await page.waitForFunction(() => document.querySelector("#save-current")?.disabled === false, undefined, {
    timeout: 10_000,
  });
  await page.locator("#save-current").evaluate((button) => button.click());
  await page.waitForFunction(
    () => /^[0-9a-f-]{36}$/u.test(document.querySelector("#capture-status")?.dataset.jobId ?? ""),
    undefined,
    { timeout: 15_000 },
  );
  const submission = await page.locator("#capture-status").evaluate((element) => ({
    jobId: element.dataset.jobId,
    status: element.textContent,
  }));
  requireCondition(
    submission.status === "Current page queued in the local companion",
    `${CURRENT_PAGE_CONFIG.metricPrefix}_capture_rejected`,
  );
  const jobId = submission.jobId;
  requireCondition(
    typeof jobId === "string" && /^[0-9a-f-]{36}$/.test(jobId),
    `${CURRENT_PAGE_CONFIG.metricPrefix}_capture_job_missing`,
  );
  await capturePage.close();
  await page.bringToFront();

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
    blocked_platform_network_requests: blockedPlatformNetworkRequests,
    fixture_documents_fulfilled: fixtureDocumentsFulfilled,
    platform_calls: platformCalls,
    platform_requests_observed: platformRequestsObserved,
    real_accounts: 0,
    request_ledger_rows: health.table_counts.request_ledger,
    screenshot,
    service_worker_restarts: restarts,
    status: "PASS",
    trace,
    wrong_statuses: wrongStatuses,
    [`${CURRENT_PAGE_CONFIG.metricPrefix}_action_before_grant_rejections`]: 2,
    [`${CURRENT_PAGE_CONFIG.metricPrefix}_action_trigger`]: "PASS_CDP_DEFAULT_ACTION",
    [`${CURRENT_PAGE_CONFIG.metricPrefix}_current_page_capture`]: "PASS_CI_SYNTH",
    [`${CURRENT_PAGE_CONFIG.metricPrefix}_owner_canary`]: "NOT_RUN",
    [`${CURRENT_PAGE_CONFIG.metricPrefix}_query_fragment_persisted`]: 0,
  };
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  if (process.env.X2N_E2E_DEBUG === "1" && !(error instanceof E2EFailure)) {
    const safeDiagnostic = String(error?.message ?? error)
      .replace(/\/(?:Users|home)\/[^/\s]+\//gu, "<local-root>/")
      .replace(/[0-9a-f]{32,}/giu, "<opaque-id>");
    process.stderr.write(`E2E_DIAGNOSTIC=${safeDiagnostic.slice(0, 400)}\n`);
  }
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
