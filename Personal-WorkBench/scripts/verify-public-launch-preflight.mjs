import { existsSync, readFileSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EVIDENCE_ROOT = join(ROOT, "13_evidence");
const TEST_EVIDENCE_FILE = process.env.NODE_ENV === "test" ? process.env.PUBLIC_LAUNCH_PREFLIGHT_EVIDENCE_FILE : null;
const EVIDENCE_FILE = TEST_EVIDENCE_FILE
  ? resolve(TEST_EVIDENCE_FILE)
  : join(EVIDENCE_ROOT, "public_launch_preflight.json");
const TASKPACK_DEFAULT_PATH = resolve(
  process.env.HOME ?? "/tmp",
  "Downloads",
  "TaskPack",
  "Personal-WorkBench",
  "胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8",
);

function runCommand(name, command, args, options = {}) {
  const child = spawnSync(command, args, {
    cwd: options.cwd || ROOT,
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${options.pathPrefix ? `${options.pathPrefix}:` : ""}${process.env.PATH || ""}`,
      ...options.env,
    },
    timeout: options.timeoutMs ?? 120_000,
    shell: process.platform === "win32",
  });

  return {
    name,
    command: `${command} ${args.join(" ")}`.trim(),
    cwd: options.cwd || ROOT,
    status: child.status ?? 1,
    signal: child.signal || null,
    stdout: (child.stdout || "").toString().trim(),
    stderr: (child.stderr || "").toString().trim(),
    ok: child.status === 0,
  };
}

function runAuthRuntimeProbe() {
  const explicit = process.env.S2_LOCAL_AUTH_ORIGIN?.trim();
  const status = runCommand(
    "npm run test:auth-runtime",
    "npm",
    ["run", "test:auth-runtime"],
    {
      cwd: ROOT,
      pathPrefix: `${join(ROOT, "node_modules", ".bin")}`,
      env: explicit ? { S2_LOCAL_AUTH_ORIGIN: explicit } : {},
    },
  );

  return {
    usedDevServer: false,
    status,
    ready: status.ok,
    mode: explicit ? "EXPLICIT_LOCAL_ORIGIN" : "IN_PROCESS_NO_SECRET_ROUTE_HARNESS",
    reason: status.ok
      ? explicit
        ? "Runtime probe passed against the explicitly supplied local origin"
        : "No-secret route boundary harness passed"
      : "Runtime probe failed",
  };
}

function readEvidence(path, fallback = null) {
  if (!existsSync(path)) return { path, exists: false, status: "MISSING", ...fallback };
  try {
    const raw = JSON.parse(readFileSync(path, "utf8"));
    return {
      path,
      exists: true,
      status: raw.status || "UNKNOWN",
      savedCandidate: raw.savedCandidate || null,
      raw,
    };
  } catch (error) {
    return {
      path,
      exists: true,
      status: "INVALID_JSON",
      error: error.message,
    };
  }
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
    saved_candidate: evidence?.savedCandidate ?? null,
  };
}

export function buildPublicDeployGates({ assetManifest, ownerActivation, authSaved, moduleMatrix }) {
  const assetRightsApproved =
    assetManifest?.status !== "PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED" &&
    assetManifest?.raw?.public_release_policy?.current_state === "APPROVED";
  const ownerActivationPassed = ownerActivation?.status === "PASS_LOCAL_OWNER_ACTIVATION_PRECHECK";
  const savedCandidatePassed =
    authSaved?.savedCandidate === "PASS" &&
    typeof authSaved?.status === "string" &&
    authSaved.status.startsWith("PASS_");
  const secondDevicePassed = moduleMatrix?.raw?.checks?.second_device_sync === "pass";

  return [
    {
      id: "authorized_public_assets",
      satisfied: assetRightsApproved,
      observed_status: assetManifest?.status ?? "MISSING",
      reason: "最终获授权 Hello Kitty 素材与权利记录必须在公开部署前通过。",
    },
    {
      id: "owner_activation",
      satisfied: ownerActivationPassed,
      observed_status: ownerActivation?.status ?? "MISSING",
      reason: "Sites 运行时配置、隐私门与 Owner 激活预检必须通过。",
    },
    {
      id: "saved_candidate_identity",
      satisfied: savedCandidatePassed,
      observed_status: authSaved?.status ?? "MISSING",
      reason: "真实 Google、邮箱、Turnstile 与回调链路必须在候选环境验证。",
    },
    {
      id: "second_device_sync",
      satisfied: secondDevicePassed,
      observed_status: moduleMatrix?.raw?.checks?.second_device_sync ?? "MISSING",
      reason: "跨设备读取与隔离必须有独立真实回放证据。",
    },
  ];
}

async function main() {
  const summary = {
    schema_version: "3.0",
    subject_phase: "PRE_S5_T1_LOCAL_PREFLIGHT",
    canonical_task: "S5-T1",
    canonical_task_completion: "NOT_GRANTED_BY_THIS_LOCAL_PRECHECK",
    status: null,
    verdict: "LOCAL_PRECHECK_ONLY",
    runAt: new Date().toISOString(),
    environment: {
      taskpack_available: existsSync(TASKPACK_DEFAULT_PATH),
      auth_runtime_mode: process.env.S2_LOCAL_AUTH_ORIGIN?.trim()
        ? "EXPLICIT_LOCAL_ORIGIN"
        : "IN_PROCESS_NO_SECRET_ROUTE_HARNESS",
      dev_probe_enabled: false,
    },
    command_results: [],
    evidence: {},
    checks: {},
    risks: [],
    next_steps: [],
  };

  const s2 = runCommand(
    "npm run test:s2",
    "npm",
    ["run", "test:s2"],
    {
      cwd: ROOT,
      pathPrefix: `${join(ROOT, "node_modules", ".bin")}`,
      timeoutMs: 300_000,
    },
  );
  const authRuntime = runAuthRuntimeProbe();
  const evidence = {
    authContract: readEvidence(join(EVIDENCE_ROOT, "auth.json")),
    authSaved: readEvidence(join(EVIDENCE_ROOT, "auth-saved.json")),
    tenantContract: readEvidence(join(EVIDENCE_ROOT, "tenant_matrix.json")),
    r2Contract: readEvidence(join(EVIDENCE_ROOT, "r2.json")),
    authRuntime: readEvidence(join(EVIDENCE_ROOT, "auth-local-runtime.json")),
    moduleMatrix: readEvidence(join(EVIDENCE_ROOT, "module_matrix.json")),
    assetManifest: readEvidence(join(EVIDENCE_ROOT, "asset_manifest.json")),
    ownerActivation: readEvidence(join(EVIDENCE_ROOT, "owner_activation.json")),
  };
  const publicDeployGates = buildPublicDeployGates({
    assetManifest: evidence.assetManifest,
    ownerActivation: evidence.ownerActivation,
    authSaved: evidence.authSaved,
    moduleMatrix: evidence.moduleMatrix,
  });
  const localPrecheckPassed = s2.ok && authRuntime.ready;

  summary.command_results = [redactCommandResult(s2), redactCommandResult(authRuntime.status)];
  summary.checks = {
    local_contract_passed: s2.ok,
    local_auth_runtime_ready: authRuntime.ready,
    public_deploy_eligible: false,
    public_deploy_authorization: "NOT_GRANTED_BY_LOCAL_PRECHECK",
    external_gates: publicDeployGates,
  };

  if (!s2.ok) {
    summary.risks.push("S2 认证/租户/API/R2 本地合同未通过；请修复本地代码后重跑。");
  }

  if (!authRuntime.ready) {
    summary.risks.push(
      `Runtime probe 未通过：${authRuntime.reason}。本地鉴权边界预检仍有缺口。`,
    );
  }

  for (const gate of publicDeployGates) {
    if (!gate.satisfied) {
      summary.risks.push(`${gate.id} 未满足：${gate.reason}（当前=${gate.observed_status}）`);
    }
  }

  if (localPrecheckPassed) {
    summary.status = "PASS_LOCAL_PUBLIC_LAUNCH_PRECHECK";
    summary.next_steps = [
      "本地预检仅证明本地合同与运行时边界；它不授予公开 Deploy 权限。",
      "完成最终获授权素材、Owner 激活、真实 OAuth/邮箱/Turnstile 与跨设备回放后，按 S5-T2/S5-T3 独立验收。",
    ];
  } else {
    summary.status = "BLOCKED_LOCAL_PUBLIC_LAUNCH_PRECHECK";
    if (summary.risks.length === 0) {
      summary.risks.push("存在未分类阻断项，需补齐本地与 Saved Candidate 路径证据。");
    }
  }

  summary.evidence = {
    auth_contract: evidenceReference(evidence.authContract, "13_evidence/auth.json"),
    auth_saved: evidenceReference(evidence.authSaved, "13_evidence/auth-saved.json"),
    tenant_contract: evidenceReference(evidence.tenantContract, "13_evidence/tenant_matrix.json"),
    r2_contract: evidenceReference(evidence.r2Contract, "13_evidence/r2.json"),
    auth_runtime: evidenceReference(evidence.authRuntime, "13_evidence/auth-local-runtime.json"),
    module_matrix: evidenceReference(evidence.moduleMatrix, "13_evidence/module_matrix.json"),
    asset_manifest: evidenceReference(evidence.assetManifest, "13_evidence/asset_manifest.json"),
    owner_activation: evidenceReference(evidence.ownerActivation, "13_evidence/owner_activation.json"),
  };

  await mkdir(dirname(EVIDENCE_FILE), { recursive: true });
  await writeFile(EVIDENCE_FILE, `${JSON.stringify(summary, null, 2)}\n`, "utf8");

  if (summary.status === "PASS_LOCAL_PUBLIC_LAUNCH_PRECHECK") {
    process.stdout.write(
      `PASS_LOCAL_PUBLIC_LAUNCH_PRECHECK ${summary.subject_phase} (public-deploy-eligible=false; external-gates-open=${summary.risks.length})\n`,
    );
  } else {
    process.stdout.write(`BLOCKED_LOCAL_PUBLIC_LAUNCH_PRECHECK ${summary.risks.length}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
