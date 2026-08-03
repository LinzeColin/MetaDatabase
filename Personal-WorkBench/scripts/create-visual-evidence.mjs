import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const taskpackRoot = process.env.TASKPACK_ROOT;
const roundArg = process.argv.indexOf("--round");
const focusArg = process.argv.indexOf("--focus");
const round = roundArg >= 0 ? Number(process.argv[roundArg + 1]) : NaN;
const focus = focusArg >= 0 ? process.argv[focusArg + 1] : "unspecified";
const visualRoot = join(root, "13_evidence", "visual");

const routes = {
  welcome: {
    reference: "01_欢迎页_视觉真值.png",
    mask: "01_欢迎页_视觉真值_mask.png",
    anchors: {
      ".welcome-kitty": [133.5, 258, 205, 202, 5],
      ".welcome-enter": [74.5, 676, 323, 63, 8],
    },
  },
  home: {
    reference: "02_桌面页_视觉真值.png",
    mask: "02_桌面页_视觉真值_mask.png",
    anchors: {
      ".sidebar": [0, 0, 88, 1024, 30],
      ".quote-card": [102, 212, 356, 111, 9],
      ".habit-card:nth-child(1)": [102, 380, 172.5, 139, 9],
      ".habit-card:nth-child(5)": [102, 679, 356, 139, 10],
    },
  },
  ledger: {
    reference: "03_记账页_视觉真值.png",
    mask: "03_记账页_视觉真值_mask.png",
    anchors: {
      ".summary-grid": [102, 84, 356, 82, 10],
      ".ledger-form": [102, 180, 356, 406, 12],
      ".record-list-card": [102, 602, 356, 158, 12],
    },
  },
  "fatloss-food": {
    reference: "04_减脂饮食页_视觉真值.png",
    mask: "04_减脂饮食页_视觉真值_mask.png",
    anchors: {
      ".module-tabs": [102, 86, 356, 52, 9],
      ".food-card": [102, 154, 356, 616, 12],
      ".upload-zone": [119, 237, 322, 130, 12],
    },
  },
  period: {
    reference: "05_经期记录页_视觉真值.png",
    mask: "05_经期记录页_视觉真值_mask.png",
    anchors: {
      ".period-form": [102, 90, 356, 169, 12],
      ".period-overview": [102, 278, 356, 151, 12],
      ".period-history": [102, 444, 356, 159, 12],
    },
  },
};

const bannedVisibleTerms = [
  "演示用户",
  "本地演示",
  "demo",
  "Better Auth",
  "Turnstile",
  "ChatGPT Sites",
  "D1",
  "R2",
  "API 密钥",
  "测试环境",
  "授权素材",
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function png(path) {
  return PNG.sync.read(readFileSync(path));
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function writePng(path, image) {
  return writeFile(path, PNG.sync.write(image));
}

function makeDiagnostic(actual, reference, mask) {
  const diff = new PNG({ width: reference.width, height: reference.height });
  const heat = new PNG({ width: reference.width, height: reference.height });
  const overlay = new PNG({ width: reference.width, height: reference.height });
  let comparedPixels = 0;
  let sum = 0;
  let significant = 0;

  for (let offset = 0; offset < reference.data.length; offset += 4) {
    const ignored = mask.data[offset] >= 128;
    const r = Math.abs(actual.data[offset] - reference.data[offset]);
    const g = Math.abs(actual.data[offset + 1] - reference.data[offset + 1]);
    const b = Math.abs(actual.data[offset + 2] - reference.data[offset + 2]);
    const mean = (r + g + b) / 3;
    const changed = !ignored && mean >= 35;
    if (!ignored) {
      comparedPixels += 1;
      sum += r + g + b;
      if (changed) significant += 1;
    }

    diff.data[offset] = changed ? Math.round(reference.data[offset] * 0.42 + 255 * 0.58) : reference.data[offset];
    diff.data[offset + 1] = changed ? Math.round(reference.data[offset + 1] * 0.42 + 50 * 0.58) : reference.data[offset + 1];
    diff.data[offset + 2] = changed ? Math.round(reference.data[offset + 2] * 0.42 + 80 * 0.58) : reference.data[offset + 2];
    diff.data[offset + 3] = 255;

    const intensity = ignored ? 245 : Math.min(255, Math.round(mean * 3));
    heat.data[offset] = intensity;
    heat.data[offset + 1] = ignored ? 245 : Math.max(0, 255 - Math.abs(intensity - 128) * 2);
    heat.data[offset + 2] = ignored ? 245 : 255 - intensity;
    heat.data[offset + 3] = 255;

    overlay.data[offset] = Math.round((actual.data[offset] + reference.data[offset]) / 2);
    overlay.data[offset + 1] = Math.round((actual.data[offset + 1] + reference.data[offset + 1]) / 2);
    overlay.data[offset + 2] = Math.round((actual.data[offset + 2] + reference.data[offset + 2]) / 2);
    overlay.data[offset + 3] = 255;
  }

  return {
    diff,
    heat,
    overlay,
    compared_pixels: comparedPixels,
    mean_absolute_rgb_difference: Number((sum / Math.max(1, comparedPixels * 3)).toFixed(3)),
    diagnostic_changed_pixel_ratio_at_threshold_35: Number((significant / Math.max(1, comparedPixels)).toFixed(5)),
  };
}

function anchorCheck(route, geometry) {
  const expected = routes[route].anchors;
  const rows = {};
  let passed = true;
  for (const [selector, [x, y, width, height, tolerance]] of Object.entries(expected)) {
    const raw = geometry.rects?.[selector];
    const actual = raw && geometry.stage
      ? { x: raw.x - geometry.stage.x, y: raw.y - geometry.stage.y, width: raw.width, height: raw.height }
      : null;
    const target = { x, y, width, height };
    const delta = actual
      ? Object.fromEntries(Object.entries(target).map(([key, value]) => [key, Number((actual[key] - value).toFixed(1))]))
      : { x: null, y: null, width: null, height: null };
    const status = actual && Object.values(delta).every((value) => Math.abs(value) <= tolerance) ? "PASS" : "FAIL";
    passed &&= status === "PASS";
    rows[selector] = { actual: actual ?? null, target, delta, tolerance_css_px: tolerance, status };
  }
  return { status: passed ? "PASS" : "FAIL", anchors: rows };
}

async function ensureResizedInputs(route, spec) {
  assert(taskpackRoot, "TASKPACK_ROOT is required to create visual evidence");
  const inputDir = join(visualRoot, "reference-inputs");
  await mkdir(inputDir, { recursive: true });
  const referenceSource = join(taskpackRoot, "02_visual", "references", spec.reference);
  const maskSource = join(taskpackRoot, "02_visual", "masks", spec.mask);
  const referenceTarget = join(inputDir, `${route}-reference.png`);
  const maskTarget = join(inputDir, `${route}-mask.png`);
  execFileSync("/usr/bin/sips", ["--resampleWidth", "472", referenceSource, "--out", referenceTarget], { stdio: "pipe" });
  execFileSync("/usr/bin/sips", ["--resampleWidth", "472", maskSource, "--out", maskTarget], { stdio: "pipe" });
  return { referenceTarget, maskTarget };
}

async function main() {
  assert(Number.isInteger(round) && round >= 1 && round <= 3, "--round must be 1, 2, or 3");
  const roundDir = join(visualRoot, `round-${round}`);
  await mkdir(roundDir, { recursive: true });
  const metrics = { schema_version: "1.0.0", round, focus, status: "PASS", routes: {} };

  for (const [route, spec] of Object.entries(routes)) {
    const actualPath = join(roundDir, `actual-${route}.png`);
    const normalizedActualPath = join(roundDir, `actual-${route}-normalized.png`);
    const geometryPath = join(roundDir, `geometry-${route}.json`);
    const [{ referenceTarget, maskTarget }, actualBytes, geometryText] = await Promise.all([
      ensureResizedInputs(route, spec),
      readFile(actualPath),
      readFile(geometryPath, "utf8"),
    ]);
    // Chrome may encode a screenshot as JPEG even when its artifact name ends in .png.
    // Normalize it before pixel comparison so the decoder and evidence format are unambiguous.
    execFileSync("/usr/bin/sips", ["--setProperty", "format", "png", actualPath, "--out", normalizedActualPath], { stdio: "pipe" });
    const actual = png(normalizedActualPath);
    const reference = png(referenceTarget);
    const mask = png(maskTarget);
    assert(actual.width === 472 && actual.height === 1024, `${route}: screenshot must be 472×1024`);
    assert(reference.width === 472 && reference.height === 1024, `${route}: scaled reference must be 472×1024`);
    assert(mask.width === 472 && mask.height === 1024, `${route}: scaled mask must be 472×1024`);
    const geometry = JSON.parse(geometryText);
    const anchor = anchorCheck(route, geometry);
    const visibleText = String(geometry.visible_text ?? "").toLowerCase();
    const banned = bannedVisibleTerms.filter((term) => visibleText.includes(term.toLowerCase()));
    const diagnostic = makeDiagnostic(actual, reference, mask);
    const { diff, heat, overlay, ...metric } = diagnostic;
    const artifactPaths = {
      actual: `13_evidence/visual/round-${round}/actual-${route}-normalized.png`,
      diff: `13_evidence/visual/round-${round}/diagnostic-diff-${route}.png`,
      heatmap: `13_evidence/visual/round-${round}/diagnostic-heatmap-${route}.png`,
      overlay: `13_evidence/visual/round-${round}/diagnostic-overlay-${route}.png`,
    };
    await Promise.all([
      writePng(join(root, artifactPaths.diff), diff),
      writePng(join(root, artifactPaths.heatmap), heat),
      writePng(join(root, artifactPaths.overlay), overlay),
    ]);
    const fixedCanvas = geometry.capture_canvas_css?.[0] === 472 && geometry.capture_canvas_css?.[1] === 1024;
    const status = anchor.status === "PASS" && banned.length === 0 && fixedCanvas && geometry.reference_mode === true && geometry.reference_page === route ? "PASS" : "FAIL";
    if (status === "FAIL") metrics.status = "FAIL";
    metrics.routes[route] = {
      status,
      capture_canvas_css: geometry.capture_canvas_css,
      browser_window_css: geometry.browser_window_css,
      screenshot_sha256: sha256(actualBytes),
      anchor,
      visible_copy_scan: { status: banned.length ? "FAIL" : "PASS", banned_terms: banned },
      visual_metric: { ...metric, status: "DIAGNOSTIC_ONLY_NOT_A_SIMILARITY_PERCENTAGE" },
      artifacts: Object.values(artifactPaths),
    };
  }

  await writeFile(join(roundDir, "metrics.json"), `${JSON.stringify(metrics, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ status: metrics.status, round, focus, routes: Object.keys(metrics.routes).length, evidence: `13_evidence/visual/round-${round}/metrics.json` }));
  if (metrics.status !== "PASS") process.exitCode = 1;
}

await main();
