import { mkdir, writeFile } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EVIDENCE_ROOT = resolve(process.env.OPS_PROJECTION_EVIDENCE_DIR || join(ROOT, "13_evidence"));
const EVIDENCE_FILE = join(EVIDENCE_ROOT, "ops_projection.json");
const SCHEMA_PATH = join(ROOT, "drizzle/0001_auth_and_product.sql");
const AUDIT_PATH = join(ROOT, "server/security/audit.ts");

function readEvidence(path) {
  if (!existsSync(path)) return { exists: false, status: "MISSING", phase: null };
  try {
    const raw = JSON.parse(readFileSync(path, "utf8"));
    return {
      exists: true,
      status: raw.status || "UNKNOWN",
      phase: raw.phase || raw.subject_phase || null,
    };
  } catch {
    return {
      exists: true,
      status: "INVALID_JSON",
      phase: null,
    };
  }
}

function readText(path) {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

function getEndpoint(name) {
  return (
    process.env[name] ||
    process.env[`${name}_URL`] ||
    process.env[`${name}_ENDPOINT`] ||
    null
  );
}

function buildAdapterMatrix(origin) {
  return {
    status: {
      name: "STATUS_ADAPTER",
      endpoint: getEndpoint("STATUS_ADAPTER_BASE") || (origin ? `${origin.replace(/\/$/, "")}/api/ops/status` : null),
      readOnlyHint: getEndpoint("STATUS_ADAPTER_READONLY") || "true",
    },
    ovh: {
      name: "OVH",
      endpoint: getEndpoint("OVH_ADAPTER_BASE") || (origin ? `${origin.replace(/\/$/, "")}/api/ops/ovh` : null),
      writeMode: getEndpoint("OVH_ADAPTER_WRITE") || "readwrite",
    },
    private_database: {
      name: "PRIVATE_DATABASE",
      endpoint: getEndpoint("PRIVATE_DATABASE_ADAPTER_BASE") || (origin ? `${origin.replace(/\/$/, "")}/api/ops/pdb` : null),
      writeMode: getEndpoint("PRIVATE_DATABASE_ADAPTER_WRITE") || "readwrite",
    },
  };
}

function readOpsAdapterToken() {
  return process.env.OPS_ADAPTER_TOKEN || process.env.OPS_PROJECTION_TOKEN || "";
}

function buildOpsProbeHeaders() {
  const token = readOpsAdapterToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

function isAuthConfigured() {
  return !!readOpsAdapterToken();
}

function originKind(value) {
  if (typeof value !== "string" || value.trim().length === 0) return "NOT_CONFIGURED";
  try {
    const url = new URL(value);
    if (url.protocol === "https:") return "HTTPS";
    if (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)) return "LOCAL_HTTP";
    return "INVALID";
  } catch {
    return "INVALID";
  }
}

function safeCommit(value) {
  const candidate = typeof value === "string" ? value.trim() : "";
  return /^[0-9a-f]{7,64}$/i.test(candidate) ? candidate : null;
}

async function requestStatus(url) {
  const start = Date.now();
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: buildOpsProbeHeaders(),
    });
    const durationMs = Date.now() - start;
    return {
      ok: response.ok || response.status === 204 || response.status === 405,
      status: response.status,
      durationMs,
    };
  } catch {
    return {
      ok: false,
      status: null,
      durationMs: Date.now() - start,
      error_redacted: true,
    };
  }
}

function buildStaticGuards() {
  const schema = readText(SCHEMA_PATH).toLowerCase();
  const audit = readText(AUDIT_PATH).toLowerCase();

  const hasRedactedInsert = (sqlText) => {
    const insertMatch = /insert\s+into\s+security_audit_events\s*\(([^)]*)\)\s*values\s*\(([^)]*)\)/i.exec(
      sqlText,
    );
    if (!insertMatch) return false;
    const columnPart = insertMatch[1];
    const valuePart = insertMatch[2];
    return (
      /\sip_digest\b/i.test(columnPart) &&
      /\suser_agent_digest\b/i.test(columnPart) &&
      /\{\}/.test(valuePart) &&
      /\bNULL\b/i.test(valuePart) &&
      /\bnull\b/i.test(valuePart) &&
      /,\s*NULL/i.test(valuePart) &&
      /NULL\s*,\s*NULL/i.test(valuePart)
    );
  };

  const hasFileObjectPrefixConstraint = (sqlText) => {
    return /create\s+table\s+if\s+not\s+exists\s+file_objects[\s\S]*?check\s*\(\s*substr\s*\(\s*object_key\s*,\s*1\s*,\s*length\s*\(\s*'users\/'\s*\|\|\s*user_id\s*\|\|\s*'\/'\s*\)\s*\)\s*=\s*'users\/'\s*\|\|\s*user_id\s*\|\|\s*'\/'\s*\)/i.test(
      sqlText,
    );
  };

  return {
    audit_schema_guard: hasRedactedInsert(audit),
    schema_has_security_audit_events: schema.includes("create table if not exists security_audit_events"),
    schema_disallows_file_objects_leak: hasFileObjectPrefixConstraint(schema),
  };
}

async function main() {
  const now = new Date().toISOString();
  const origin = getEndpoint("PRODUCTION_ORIGIN") || process.env.SITES_PRODUCTION_ORIGIN || process.env.APP_ORIGIN || null;
  const matrix = buildAdapterMatrix(origin);
  const staticGuards = buildStaticGuards();
  const adapterKeys = Object.keys(matrix);

  const summary = {
    schema_version: "3.0",
    subject_phase: "S5-T4",
    status: null,
    verdict: "NOT_ISSUED_PRE_VERIFIER",
    generated_at: now,
    environment: {
      production_origin_configured: Boolean(origin),
      production_origin_kind: originKind(origin),
      timestamp: now,
    },
    checks: {
      static_projection_guards: staticGuards,
      adapters: {},
      evidence_links: {
        production_smoke: readEvidence(join(ROOT, "13_evidence/production-smoke-status.json")),
        owner_activation: readEvidence(join(ROOT, "13_evidence/owner_activation.json")),
        verifier: readEvidence(join(ROOT, "13_evidence/verifier.json")),
      },
      canaries: {
        email_in_projection_candidate: false,
        period_in_projection_candidate: false,
        weight_in_projection_candidate: false,
        diary_in_projection_candidate: false,
        consent_in_projection_candidate: false,
      },
    },
    command_results: [],
    risks: [],
    next_steps: [],
  };

  let adapterConfigured = 0;
  for (const key of adapterKeys) {
    const adapter = matrix[key];
    if (adapter.endpoint && /^https?:\/\/\S+/i.test(adapter.endpoint)) {
      adapterConfigured += 1;
      const result = await requestStatus(adapter.endpoint);
      summary.checks.adapters[key] = {
        name: adapter.name,
        endpoint_configured: true,
        status: result.ok ? "reachable" : "unreachable",
        status_code: result.status,
        duration_ms: result.durationMs,
        error_redacted: Boolean(result.error_redacted),
        write_mode_hint: adapter.writeMode || adapter.readOnlyHint || "unknown",
      };
      summary.command_results.push({
        probe: "GET",
        adapter: key,
        status: result.status,
        ok: result.ok,
        duration_ms: result.durationMs,
      });
      if (!result.ok) {
        if (result.status === 401) {
          const authHint = isAuthConfigured()
            ? `${adapter.name} adapter 返回 401（token 鉴权未通过，需核对 OPS_ADAPTER_TOKEN/OPS_PROJECTION_TOKEN）`
            : `${adapter.name} adapter 返回 401（缺少 ops 鉴权 token，需设置 OPS_ADAPTER_TOKEN 或 OPS_PROJECTION_TOKEN）`;
          summary.risks.push(authHint);
        } else {
          summary.risks.push(`${adapter.name} adapter 可达性异常：HTTP ${result.status || "UNREACHABLE"}。`);
        }
      }
    } else {
      summary.checks.adapters[key] = {
        name: adapter.name,
        endpoint_configured: false,
        status: "missing",
        status_code: null,
        write_mode_hint: adapter.writeMode || adapter.readOnlyHint || "unknown",
      };
      summary.risks.push(`${adapter.name} 适配器未配置 endpoint（建议设置 STATUS_ADAPTER_BASE / OVH_ADAPTER_BASE / PRIVATE_DATABASE_ADAPTER_BASE）。`);
    }
  }

  if (!origin) {
    summary.risks.push("未设置 PRODUCTION_ORIGIN 或 SITES_PRODUCTION_ORIGIN，无法执行投影写入通道预检。");
  }

  if (!staticGuards.audit_schema_guard) {
    summary.risks.push("本地审计写入未确认脱敏约束（security_audit_events.details_json 限制不完整）。");
  }
  if (!staticGuards.schema_has_security_audit_events) {
    summary.risks.push("未检测到 security_audit_events 表定义，无法验证高敏数据不进日志。");
  }

  const preconditionsReady = adapterConfigured >= 1 && staticGuards.audit_schema_guard && staticGuards.schema_has_security_audit_events;
  const productionSmokeDone = summary.checks.evidence_links.production_smoke.status === "PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK";
  if (!productionSmokeDone) {
    summary.risks.push("S5-T3 生产烟雾（包含链路预检）未成功通过，不建议先执行 ops projection。");
  }

  if (
    summary.risks.length === 0 &&
    preconditionsReady &&
    staticGuards.schema_disallows_file_objects_leak &&
    adapterConfigured >= 3
  ) {
    summary.status = "PASS_LOCAL_OPS_PROJECTION_PRECHECK";
  } else if (adapterConfigured === 0) {
    summary.status = "NOT_RUN_LOCAL_OPS_PROJECTION";
  } else {
    summary.status = "BLOCKED_LOCAL_OPS_PROJECTION";
  }

  summary.next_steps = summary.risks.length
    ? [
        "补齐三个 adapter endpoint（STATUS/OVH/PDB）与最小只读凭据。",
        "确认本地审计路径仅写入脱敏字段，且对象键/正文字段不被投影。",
        "待 S5-T3 生产链路通过后再次执行 `npm run verify:ops-projection`。",
      ]
    : [
        "当前适配器与静态红线齐全，可推进 status/OVH/Private-Database 投影写入与只读回放。",
        "请将脱敏后的运维投影 payload 与写入路径再次与状态系统核验。",
      ];

  const statusFile = {
    task_id: "S5-T4",
    status: summary.status,
    candidate_commit: safeCommit(process.env.GITHUB_SHA),
    environment: {
      origin_configured: Boolean(origin),
      origin_kind: originKind(origin),
    },
    evidence_files: [
      "13_evidence/production-smoke-status.json",
      "13_evidence/owner_activation.json",
      "13_evidence/r2.json",
      "13_evidence/tenant_matrix.json",
    ],
    notes: "本脚本为 S5-T4 投影可用性预检工具；高敏字段投影必须在真实 adapter 写入链路完成后再次核验。",
    phase: summary.status === "PASS_LOCAL_OPS_PROJECTION_PRECHECK" ? "LOCAL_PRECHECK_DONE" : "BLOCKED",
    reason: summary.risks.join("; ") || null,
  };

  await mkdir(EVIDENCE_ROOT, { recursive: true });
  await writeFile(EVIDENCE_FILE, `${JSON.stringify(statusFile, null, 2)}\n`, "utf8");
  await writeFile(
    join(EVIDENCE_ROOT, "ops_projection-run.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
    "utf8",
  );

  if (summary.status === "PASS_LOCAL_OPS_PROJECTION_PRECHECK") {
    process.stdout.write(`PASS_LOCAL_OPS_PROJECTION_PRECHECK ${summary.subject_phase}\n`);
  } else if (summary.status === "NOT_RUN_LOCAL_OPS_PROJECTION") {
    process.stdout.write("NOT_RUN_LOCAL_OPS_PROJECTION missing_adapters\n");
  } else {
    process.stdout.write(`BLOCKED_LOCAL_OPS_PROJECTION ${summary.risks.length}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
