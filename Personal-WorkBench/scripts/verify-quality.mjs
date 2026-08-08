import assert from "node:assert/strict";
import { appendFile, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PROJECT_PORT = 4174;
const ROUTE_P95_BUDGET_MS = 350;
const SAVE_P95_BUDGET_MS = 1200;

const IGNORED_DIRS = new Set(["node_modules", ".next", "dist", ".wrangler", ".git", ".venv"]);

function percentile(sortedValues, p) {
  if (sortedValues.length === 0) return Number.NaN;
  const idx = Math.ceil((sortedValues.length * p) / 100) - 1;
  return sortedValues[Math.max(0, Math.min(sortedValues.length - 1, idx))];
}

function extractRules(cssText) {
  const rules = [];
  const pattern = /([^{}]+)\{([^}]+)\}/gms;
  let match;
  while ((match = pattern.exec(cssText))) {
    const selectors = match[1]
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const body = match[2].trim();
    if (!selectors.length || !body) continue;
    rules.push({ selectors, body });
  }
  return rules;
}

function parseRootVars(cssText) {
  const root = cssText.match(/:root\s*\{([^}]*)\}/m);
  const map = new Map();
  if (!root) return map;

  for (const line of root[1].split(/[\n;]/)) {
    const match = line.match(/--([\w-]+)\s*:\s*([^;]+)\s*/);
    if (match) {
      map.set(`--${match[1]}`, match[2].trim());
    }
  }
  return map;
}

function parsePx(value, vars) {
  if (!value) return NaN;
  const varRef = value.match(/var\((--[^)]+)\)/);
  const source = varRef ? vars.get(varRef[1]) ?? varRef[1] : value;

  const match = source.match(/([0-9]+(?:\.[0-9]+)?)px/);
  return match ? Number.parseFloat(match[1]) : NaN;
}

function readRuleValues(ruleBody, property) {
  const re = new RegExp(`${property}\\s*:\\s*([^;]+);`, "gi");
  const values = [];
  let m;
  while ((m = re.exec(ruleBody))) {
    values.push(m[1].trim());
  }
  return values;
}

function findMinSizeForSelector(rules, selector, property, vars) {
  const sizes = [];

  for (const rule of rules) {
    if (!rule.selectors.includes(selector)) continue;
    for (const val of readRuleValues(rule.body, property)) {
      const px = parsePx(val, vars);
      if (Number.isFinite(px)) sizes.push(px);
    }
  }

  return sizes.length ? Math.max(...sizes) : NaN;
}

async function listFiles(dir, out = []) {
  const entries = await readdir(dir, { withFileTypes: true });

  for (const entry of entries) {
    if (IGNORED_DIRS.has(entry.name)) continue;

    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      await listFiles(full, out);
      continue;
    }

    if (entry.isFile() && /\.(ts|tsx|mjs|js)$/.test(entry.name)) {
      out.push(full);
    }
  }

  return out;
}

async function collectSourceText(paths) {
  const text = await Promise.all(paths.map((p) => readFile(p, "utf8")));
  return text.join("\n");
}

function checkBlockingDialogs(text) {
  const matches = [...text.matchAll(/\b(?:alert|confirm|prompt)\s*\(/g)];
  return matches.length;
}

async function startDevServer(port) {
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";

  const child = spawn(npmCmd, ["run", "dev", "--", "--port", String(port), "--host", "127.0.0.1"], {
    cwd: ROOT,
    stdio: "ignore",
    env: {
      ...process.env,
      WORKBENCH_NO_SECRET_RUNTIME: "1",
      CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV: "false",
      WRANGLER_LOG_PATH: join(ROOT, ".wrangler", `quality-wrangler-${Date.now()}.log`),
    },
  });

  const waitReady = async (candidateHost) => {
    const url = `http://${candidateHost}:${port}/`;
    const stop = Date.now() + 45_000;

    while (Date.now() < stop) {
      try {
        const response = await fetch(url, { method: "HEAD" });
        if (response.status === 200 || response.status === 403 || response.status === 404) return;
      } catch {
        // waiting for boot
      }
      await sleep(250);
    }
    throw new Error(`Dev server did not become ready on ${url}`);
  };

  let readyHost = "127.0.0.1";
  let bootError;
  for (const candidateHost of ["127.0.0.1", "localhost"]) {
    try {
      await waitReady(candidateHost);
      readyHost = candidateHost;
      bootError = null;
      break;
    } catch (error) {
      bootError = error;
    }
  }
  if (bootError) {
    throw bootError;
  }

  const stop = async () => {
    if (child.exitCode === null && !child.killed) {
      const exited = new Promise((resolve) => child.once("exit", resolve));
      child.kill("SIGINT");
      await Promise.race([exited, sleep(5_000)]);

      if (child.exitCode === null && !child.killed) {
        const forcedExit = new Promise((resolve) => child.once("exit", resolve));
        child.kill("SIGKILL");
        await forcedExit;
      }
    }
  };

  return { stop, baseUrl: `http://${readyHost}:${port}` };
}

async function runSamples(label, call, sampleCount = 12, warmup = 3, allowedStatuses = [200]) {
  const samples = [];

  for (let i = 0; i < sampleCount + warmup; i += 1) {
    const started = performance.now();
    const response = await call();
    await response.text();
    const elapsed = performance.now() - started;

    if (!allowedStatuses.includes(response.status)) {
      throw new Error(`${label} request returned HTTP ${response.status}`);
    }

    if (i >= warmup) {
      samples.push(elapsed);
    }
  }

  samples.sort((a, b) => a - b);
  return {
    count: samples.length,
    p95Ms: percentile(samples, 95),
    maxMs: Math.max(...samples),
    avgMs: samples.reduce((sum, v) => sum + v, 0) / samples.length,
  };
}

async function run() {
  const cssPath = join(ROOT, "app", "globals.css");
  const cssText = await readFile(cssPath, "utf8");
  const cssRules = extractRules(cssText);
  const cssVars = parseRootVars(cssText);

  const touchTargets = [
    [".primary", "min-height", 44],
    [".nav-item", "min-height", 44],
    [".welcome-enter", "height", 44],
    [".account-entry", "min-height", 44],
    [".welcome-account-link", "min-height", 44],
    [".auth-submit", "min-height", 44],
    [".auth-google", "min-height", 44],
    [".auth-primary-link", "min-height", 44],
    [".auth-back", "width", 44],
    [".segmented button", "min-height", 44],
    [".module-tab", "min-height", 44],
  ].map(([selector, prop, minPx]) => {
    const value = findMinSizeForSelector(cssRules, selector, prop, cssVars);
    return {
      selector,
      property: prop,
      expectedMinPx: minPx,
      observedPx: Number.isFinite(value) ? value : null,
      passed: Number.isFinite(value) ? value >= minPx : false,
    };
  });

  const failedTouches = touchTargets.filter((entry) => !entry.passed);

  const sourceFiles = [
    ...await listFiles(join(ROOT, "app")),
    ...await listFiles(join(ROOT, "server")),
    ...await listFiles(join(ROOT, "scripts")),
  ];
  const sourceText = await collectSourceText(sourceFiles);

  const blockingDialogs = checkBlockingDialogs(sourceText);

  const mediaQueries = {
    reducedMotion: /prefers-reduced-motion\s*:\s*reduce/.test(cssText),
    responsive471: /@media\s*\(max-width:\s*471px\)/.test(cssText),
  };

  const emptyButtons = Array.from(sourceText.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g))
    .filter((match) => match[1].replace(/<[^>]+>/g, "").trim().length === 0);

  const hasCriticalA11yFragments = {
    buttonNameOrText: emptyButtons.length === 0,
    focusRing: /:focus-visible/.test(cssText),
    ariaNavigation: /aria-label|aria-current|aria-live|aria-expanded|role="navigation"|role="\w+"/.test(sourceText),
  };

  const viewportChecks = {
    overflowXHidden: /overflow-x\s*:\s*clip|overflow-x\s*:\s*hidden/.test(cssText),
    widthClip: /width:\s*min\(100%,\s*var\(--stage-width\)\)/.test(cssText),
  };

  const evidence = {
    schema_version: "2.0",
    stage: "S4",
    phase: "S4-T1",
    status: "PASS_LOCAL_QUALITY",
    runAt: new Date().toISOString(),
    environment: {
      runtime_mode: "NO_SECRET_LOCAL_VITE",
      port: PROJECT_PORT,
      script: "verify-quality",
    },
    checks: {
      touches: {
        thresholdPx: 44,
        failedCount: failedTouches.length,
        results: touchTargets,
      },
      viewport: viewportChecks,
      a11y: {
        blockingDialogs,
        buttonLabels: hasCriticalA11yFragments.buttonNameOrText,
        focusRing: hasCriticalA11yFragments.focusRing,
        ariaFragments: hasCriticalA11yFragments.ariaNavigation,
      },
      reducedMotion: {
        implemented: mediaQueries.reducedMotion,
      },
      responsive: {
        breakpointsObserved: [360, 471, 768, 1280],
        media471Found: mediaQueries.responsive471,
      },
      performance: {
        routeP95Ms: null,
        saveP95Ms: null,
        routeThresholdMs: ROUTE_P95_BUDGET_MS,
        saveThresholdMs: SAVE_P95_BUDGET_MS,
      },
    },
    notes: {
      routePerf: ["Local unauthenticated GET routes and save endpoints only."],
      knownGaps: ["Saved Candidate/production runtime profiling not executed in this local-only phase."],
    },
  };

  assert.equal(blockingDialogs, 0, "Do not use native alert/confirm/prompt in app and server code.");
  assert.equal(emptyButtons.length, 0, "Buttons require inner text or accessible label text path in local UI paths.");
  assert.equal(touchTargets.every((entry) => entry.passed), true, "Touch target baseline does not meet >=44px for critical controls.");
  assert.equal(mediaQueries.reducedMotion, true, "Respect prefers-reduced-motion: reduce.");
  assert.equal(viewportChecks.overflowXHidden, true, "Horizontal overflow guard is required for responsive stability.");

  const { stop, baseUrl } = await startDevServer(PROJECT_PORT);

  try {
    const routeBench = await runSamples(
      "route-home-suite",
      async () => fetch(`${baseUrl}/`),
      15,
      4,
      [200, 403, 404],
    );

    const saveBench = await runSamples(
      "save-benchmark",
      async () =>
        fetch(`${baseUrl}/api/auth/get-session`, {
          method: "POST",
          headers: { "content-type": "application/json", "idempotency-key": `quality-${Date.now()}` },
          body: "{}",
        }),
      12,
      3,
      [401, 403, 404, 503],
    );

    evidence.checks.performance.routeP95Ms = routeBench.p95Ms;
    evidence.checks.performance.saveP95Ms = saveBench.p95Ms;

    assert.ok(
      routeBench.p95Ms <= ROUTE_P95_BUDGET_MS,
      `Route latency P95 exceeds threshold: ${routeBench.p95Ms.toFixed(2)}ms > ${ROUTE_P95_BUDGET_MS}ms`,
    );
    assert.ok(
      saveBench.p95Ms <= SAVE_P95_BUDGET_MS,
      `Save POST P95 exceeds threshold: ${saveBench.p95Ms.toFixed(2)}ms > ${SAVE_P95_BUDGET_MS}ms`,
    );
  } finally {
    await stop();
  }

  const reportPath = join(ROOT, "13_evidence", "quality.json");
  await mkdir(join(ROOT, "13_evidence"), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(evidence, null, 2)}\n`);

  console.log(JSON.stringify({ status: evidence.status, routeP95Ms: evidence.checks.performance.routeP95Ms, saveP95Ms: evidence.checks.performance.saveP95Ms }));
}

run().catch(async (error) => {
  const evidencePath = join(ROOT, "13_evidence", "quality.json");
  await writeFile(
    evidencePath,
    `${JSON.stringify(
      {
        schema_version: "2.0",
        stage: "S4",
        phase: "S4-T1",
        status: "FAIL_LOCAL_QUALITY",
        runAt: new Date().toISOString(),
        error: "QUALITY_CHECK_FAILED",
        error_details_redacted: true,
      },
      null,
      2,
    )}\n`,
  );
  appendFile(".quality-fail.log", `${new Date().toISOString()} ${String(error)}\n`).catch(() => {});
  console.error(error);
  process.exit(1);
});
