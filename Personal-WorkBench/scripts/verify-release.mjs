import { mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TASKPACK_VERSION = "v0.0.0.8";
const TARGET_PROJECT = "胡楚靓工作台";
const TASKPACK_DEFAULT_PATH = resolve(
  process.env.HOME ?? "/tmp",
  "Downloads",
  "TaskPack",
  "Personal-WorkBench",
  "胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8",
);

function fail(message) {
  throw new Error(message);
}

function runCommand(name, command, args, options = {}) {
  const child = spawnSync(command, args, {
    cwd: options.cwd || ROOT,
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${options.pathPrefix ? `${options.pathPrefix}:` : ""}${process.env.PATH || ""}`,
    },
    timeout: options.timeoutMs ?? 120_000,
    shell: process.platform === "win32",
  });

  return {
    name,
    command: `${command} ${args.join(" ")}`.trim(),
    status: child.status ?? 1,
    signal: child.signal || null,
    stdout: (child.stdout || "").toString().trim(),
    stderr: (child.stderr || "").toString().trim(),
    ok: child.status === 0,
  };
}

export function redactCommandResult(result) {
  return {
    name: result.name,
    command: result.command,
    status: result.status,
    signal: result.signal,
    ok: result.ok,
    output_redacted: Boolean(result.stdout || result.stderr),
  };
}

export function evidenceReference(evidence, source) {
  return {
    source,
    exists: evidence?.exists === true,
    status: evidence?.status ?? "UNKNOWN",
    phase: evidence?.phase ?? null,
    run_at: evidence?.runAt ?? null,
  };
}

function parseJson(text, fallbackContext) {
  try {
    if (!text) return null;
    const trimmed = text.trim();
    const jsonStart = trimmed.indexOf("{");
    const jsonText = jsonStart >= 0 ? trimmed.slice(jsonStart) : trimmed;
    return JSON.parse(jsonText);
  } catch {
    throw new Error(`无法解析 ${fallbackContext} JSON 输出`);
  }
}

function resolveTaskpackRoot() {
  const explicit = process.env.TASKPACK_ROOT && resolve(process.env.TASKPACK_ROOT);
  const candidates = [explicit, TASKPACK_DEFAULT_PATH].filter(Boolean);

  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    if (existsSync(join(candidate, "CANONICAL_STATE.json")) && existsSync(join(candidate, "06_tasks", "TASK_DAG.json"))) {
      return resolve(candidate);
    }
  }

  return null;
}

function readEvidence(path) {
  if (!existsSync(path)) {
    return { exists: false, status: "MISSING", phase: null, runAt: null, raw: null };
  }

  try {
    const raw = JSON.parse(readFileSync(path, "utf8"));
    return {
      exists: true,
      status: raw.status || "UNKNOWN",
      phase: raw.phase || null,
      runAt: raw.runAt || null,
      raw,
    };
  } catch {
    return { exists: true, status: "INVALID_JSON", phase: null, runAt: null, raw: null };
  }
}

function isPassEvidence(evidence) {
  return Boolean(
    evidence?.exists &&
      typeof evidence.status === "string" &&
      evidence.status.startsWith("PASS"),
  );
}

export async function main() {
  const summary = {
    schema_version: "3.0",
    target_project: TARGET_PROJECT,
    product_version: TASKPACK_VERSION,
    subject_phase: "S4-T3",
    status: null,
    verdict: null,
    runAt: new Date().toISOString(),
    command_results: [],
    taskpack_available: false,
    taskpack_check: {
      status: "NOT_RUN",
      phase: null,
      command_output_redacted: false,
    },
    evidence: {},
    risks: [],
    notes: [],
  };
  const commandResults = [];
  let failed = false;

  try {
    const taskpackRoot = resolveTaskpackRoot();
    if (!taskpackRoot) fail("TASKPACK_UNAVAILABLE");
    summary.taskpack_available = true;

    const precheckCommands = [
      { name: "npm run test:quality", command: "npm", args: ["run", "test:quality"] },
      { name: "npm run test:visual", command: "npm", args: ["run", "test:visual"] },
      { name: "npm run test:resilience", command: "npm", args: ["run", "test:resilience"] },
    ];

    for (const item of precheckCommands) {
      const result = runCommand(item.name, item.command, item.args, {
        cwd: ROOT,
        pathPrefix: `${ROOT}/node_modules/.bin`,
      });
      commandResults.push(result);
      if (!result.ok) fail("LOCAL_PRECHECK_FAILED");
    }

    const taskpackVerifier = runCommand(
      "python3 12_scripts/verify_taskpack.py",
      "python3",
      ["12_scripts/verify_taskpack.py"],
      { cwd: taskpackRoot, pathPrefix: `${join(ROOT, "node_modules", ".bin")}` },
    );
    commandResults.push(taskpackVerifier);
    if (!taskpackVerifier.ok) fail("TASKPACK_VERIFIER_FAILED");

    const taskpackOutput = parseJson(taskpackVerifier.stdout, "verify_taskpack");
    summary.taskpack_check = {
      status: taskpackOutput?.status || "UNKNOWN",
      phase: taskpackOutput?.phase || null,
      command_output_redacted: Boolean(taskpackVerifier.stdout || taskpackVerifier.stderr),
    };
    if (taskpackOutput?.status !== "PASS_FOR_SEALED_TASKPACK") fail("TASKPACK_VERIFIER_NOT_PASS");

    const evidence = {
      quality: readEvidence(join(ROOT, "13_evidence", "quality.json")),
      visual: readEvidence(join(ROOT, "13_evidence", "visual", "manifest.json")),
      resilience: readEvidence(join(ROOT, "13_evidence", "resilience.json")),
    };
    summary.evidence = {
      quality: evidenceReference(evidence.quality, "13_evidence/quality.json"),
      visual: evidenceReference(evidence.visual, "13_evidence/visual/manifest.json"),
      resilience: evidenceReference(evidence.resilience, "13_evidence/resilience.json"),
    };

    const blocked = [];
    if (!isPassEvidence(evidence.quality)) blocked.push("本地可访问性质量证据缺失或未通过");
    if (!isPassEvidence(evidence.visual)) blocked.push("视觉真值验收证据缺失或未通过");
    if (!isPassEvidence(evidence.resilience)) blocked.push("离线恢复验收证据缺失或未通过");

    if (blocked.length > 0) {
      summary.status = "FAIL_LOCAL_RELEASE_PRECHECK";
      summary.verdict = "BLOCKED_BY_PRECHECK";
      summary.risks = blocked;
      summary.notes.push("本次为 Builder 本地冻结准备；正式 Verifier 未执行。未通过预检时不进入 S5。");
      failed = true;
    } else {
      summary.status = "PASS_BUILD_LAST_MILE_READINESS";
      summary.verdict = "NOT_ISSUED_PRE_VERIFIER";
      summary.risks = [
        "Saved Candidate 未运行；环境边界与正式 OAuth/邮件/Google/Turnstile 未覆盖",
        "该本地预检不转化为正式产品 PASS 或公开 Deploy 权限",
      ];
      summary.notes.push("该结果只用于冻结候选准备；最终产品裁决需由独立 Verifier 在 FROZEN_CANDIDATE 上重跑。");
    }
  } catch {
    summary.status = "FAIL_LOCAL_RELEASE_PRECHECK";
    summary.verdict = "BLOCKED_BY_PRECHECK";
    summary.risks = ["本地冻结预检未通过；请检查已记录命令状态后重跑。"];
    summary.notes.push("命令原始输出不会写入证据；失败不构成正式产品裁决。");
    failed = true;
  }

  summary.command_results = commandResults.map(redactCommandResult);
  await mkdir(join(ROOT, "13_evidence"), { recursive: true });
  await writeFile(join(ROOT, "13_evidence", "verifier.json"), `${JSON.stringify(summary, null, 2)}\n`, "utf8");

  if (failed) {
    console.log("FAIL_LOCAL_RELEASE_PRECHECK", summary.risks.length);
    process.exitCode = 1;
  } else {
    console.log("PASS_BUILD_LAST_MILE_READINESS", "verifier.json");
  }

  return summary;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
