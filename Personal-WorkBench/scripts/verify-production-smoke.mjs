import { writeFile } from "node:fs/promises";
import { mkdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EVIDENCE_ROOT = resolve(process.env.PRODUCTION_SMOKE_EVIDENCE_DIR || join(ROOT, "13_evidence"));
const EVIDENCE_FILE = join(EVIDENCE_ROOT, "production.json");

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

function getProductionOrigin() {
  return (
    process.env.SITES_PRODUCTION_ORIGIN ||
    process.env.PRODUCTION_SMOKE_ORIGIN ||
    process.env.SMOKE_ORIGIN ||
    process.env.APP_ORIGIN ||
    null
  );
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function originKind(value) {
  if (!isNonEmptyString(value)) return "NOT_CONFIGURED";
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

function isValidSmokeOrigin(value, allowHttp = false) {
  if (!isNonEmptyString(value)) return false;
  try {
    const url = new URL(value);
    if (url.protocol === "https:") return true;
    if (!allowHttp) return false;
    if (url.protocol !== "http:") return false;
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return false;
    return true;
  } catch {
    return false;
  }
}

function summarizePath(route, response, didFail = false) {
  if (didFail) {
    return {
      route,
      ok: false,
      status: null,
      reason: "REQUEST_FAILED",
      duration_ms: null,
    };
  }
  return {
    route,
    ok: response.ok,
    status: response.status,
    reason: response.status >= 200 && response.status < 500 ? "HTTP_REACHABLE" : "UNEXPECTED_STATUS",
    duration_ms: response.durationMs,
  };
}

async function requestWithStatus(url, options = {}) {
  const start = Date.now();
  try {
    const response = await fetch(url, {
      method: options.method || "GET",
      headers: options.headers || {},
      signal: options.signal,
    });
    const durationMs = Date.now() - start;
    return {
      ok: response.ok,
      status: response.status,
      durationMs,
    };
  } catch (error) {
    return {
      ok: false,
      status: null,
      durationMs: Date.now() - start,
      error: Boolean(error),
    };
  }
}

async function canResolveOrigin(origin) {
  try {
    const parsed = new URL(`${origin}/`);
    const allowInsecure = process.env.ALLOW_HTTP_SMOKE_ORIGIN === "1";
    if (parsed.protocol !== "https:" && !(allowInsecure && parsed.protocol === "http:")) return false;
    const result = await requestWithStatus(`${origin}/`);
    return result.ok || result.status === 301 || result.status === 302 || result.status === 200;
  } catch {
    return false;
  }
}

async function main() {
  const now = new Date().toISOString();
  const productionOrigin = getProductionOrigin();

  const summary = {
    schema_version: "3.0",
    subject_phase: "S5-T3",
    status: null,
    verdict: "NOT_ISSUED_PRE_VERIFIER",
    generated_at: now,
    environment: {
      production_origin_configured: Boolean(productionOrigin),
      production_origin_kind: originKind(productionOrigin),
      can_resolve_origin: productionOrigin ? await canResolveOrigin(productionOrigin) : false,
    },
    checks: {
      routes: {
        root: null,
        sign_in: null,
        sign_up: null,
        forgot_password: null,
        verify_email: null,
        public_config: null,
        profile_probe: null,
      },
      production_assets: {
        candidate_version_probe: null,
      },
      credentials: {
        has_google_live_account: isNonEmptyString(process.env.SITES_SMOKE_GOOGLE_EMAIL),
        has_mail_account: isNonEmptyString(process.env.SITES_SMOKE_EMAIL),
        has_password: isNonEmptyString(process.env.SITES_SMOKE_PASSWORD),
      },
      evidence_links: {
        owner_activation: readEvidence(join(ROOT, "13_evidence/owner_activation.json")),
        auth_saved: readEvidence(join(ROOT, "13_evidence/auth-saved.json")),
      },
    },
    command_results: [],
    risks: [],
    next_steps: [],
  };

  const allowInsecure = process.env.ALLOW_HTTP_SMOKE_ORIGIN === "1";

  if (!productionOrigin) {
    summary.risks.push("未设置生产 Origin（需配置 SITES_PRODUCTION_ORIGIN 或 PRODUCTION_SMOKE_ORIGIN）。");
  } else if (!isValidSmokeOrigin(productionOrigin, allowInsecure)) {
    summary.risks.push("生产 Origin 非法或不满足 HTTPS/本地 HTTP 安全策略。");
  }

  if (!productionOrigin || !isValidSmokeOrigin(productionOrigin, allowInsecure)) {
    summary.status = "BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK";
    summary.next_steps = [
      "先设置生产环境地址（推荐 SITES_PRODUCTION_ORIGIN=https://xxx.pages.dev 或正式域名）。",
      "完成 Sites Saved Candidate 部署并发布可访问 URL 后再执行本脚本。",
      "生产 Origin 可达后执行 `npm run verify:owner-activation` 与 `npm run verify:public-launch` 复核环境门槛。",
    ];
  } else {
    const timeoutMs = 12000;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
    const checks = [
        { key: "root", route: "/" },
        { key: "sign_in", route: "/auth/sign-in" },
        { key: "sign_up", route: "/auth/sign-up" },
        { key: "forgot_password", route: "/auth/forgot-password" },
        { key: "verify_email", route: "/auth/verify-email" },
        { key: "public_config", route: "/api/auth/public-config" },
        { key: "profile_probe", route: "/api/mydairy/profile" },
      ];

      for (const item of checks) {
        const result = await requestWithStatus(`${productionOrigin}${item.route}`, {
          method: "GET",
          signal: controller.signal,
        });
        const check = summarizePath(item.route, {
          ok: result.ok,
          status: result.status,
          durationMs: result.durationMs,
        }, result.error);
        summary.checks.routes[item.key] = check;
        summary.command_results.push({
          probe: "GET",
          route: item.route,
          status: result.status,
          ok: result.ok,
          elapsed_ms: result.durationMs,
        });
      }

      if (summary.checks.routes.profile_probe?.status !== 401 && summary.checks.routes.profile_probe?.status !== 403) {
        summary.risks.push("未认证访问 /api/mydairy/profile 未返回 401/403，鉴权边界不满足预期。");
      }

      if (summary.checks.routes.sign_in?.status >= 500) {
        summary.risks.push("/auth/sign-in 返回 5xx，生产鉴权页面不可用。");
      }

      if (summary.checks.routes.public_config?.status !== 200) {
        summary.risks.push(`/api/auth/public-config 返回 ${summary.checks.routes.public_config?.status || "UNREACHABLE"}，客户端配置接口异常。`);
      }

      if (!summary.checks.credentials.has_mail_account || !summary.checks.credentials.has_password) {
        summary.risks.push("尚未注入生产真实账号验证流水线所需凭据（SITES_SMOKE_EMAIL / SITES_SMOKE_PASSWORD）。");
      }

      if (!summary.checks.credentials.has_google_live_account) {
        summary.risks.push("尚未注入 Google 实时回放用账户（SITES_SMOKE_GOOGLE_EMAIL）。");
      }

      if (summary.risks.length === 0) {
        summary.risks.push("生产真实 OAuth/邮件注册/找回/会话链路仍未执行，请由外部 Saved Candidate 与人工/自动化流程完成后回填。");
      }

      if (summary.risks.length === 0) {
        summary.status = "PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK";
      } else {
        summary.status = "BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK";
      }

      summary.checks.production_assets.candidate_version_probe = {
        candidate_hint: "PRODUCTION_SMOKE does not auto-deploy; capture version externally",
        status: "NOT_EXECUTED",
      };
    } catch {
      summary.risks.push("PRODUCTION_SMOKE_EXCEPTION");
      summary.status = "BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK";
      summary.command_results.push({
        probe: "production-smoke-batch",
        status: null,
        ok: false,
        elapsed_ms: 0,
        error_redacted: true,
      });
    } finally {
      clearTimeout(timeout);
      controller.abort();
    }
  }

  if (!summary.next_steps.length) {
    if (summary.status === "PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK") {
      summary.next_steps = [
        "基础 URL/鉴权页可达且鉴权边界满足；请继续执行生产真实 OAuth/邮件找回/多设备/跨租户链路。",
        "在 real flow 成功后更新 evidence 并推进 `npm run verify:ops-projection`。",
      ];
    } else {
      summary.next_steps = [
        "按阻断项补齐生产 Origin、真实账户凭据与回调环境。",
        "优先完成 OAuth callback、邮件发送域、Turnstile 与生产 Side-effect 授权后重跑。",
        "生产真实链路通过后，将 `SITES_SMOKE_EMAIL`、`SITES_SMOKE_PASSWORD` 与 Google 测试账户用于真实回放。",
      ];
    }
  }

  const statusFile = {
    task_id: "S5-T3",
    status: summary.status,
    candidate_commit: safeCommit(process.env.GITHUB_SHA),
    environment: {
      origin_configured: Boolean(productionOrigin),
      origin_kind: originKind(productionOrigin),
      checked_at: now,
    },
    evidence_files: [
      "13_evidence/auth-saved.json",
      "13_evidence/owner_activation.json",
      "13_evidence/asset_manifest.json",
    ],
    notes: "生产链路验证脚本先输出可复现的预检阻断信息，真实 OAuth/邮箱/回归脚本需在生产域名下另行执行。",
    phase: summary.status.startsWith("PASS") ? "READY_FOR_SAVED_CANDIDATE_REAL" : "BLOCKED",
    reason: summary.risks.join("; ") || null,
  };

  await mkdir(EVIDENCE_ROOT, { recursive: true });
  await writeFile(EVIDENCE_FILE, `${JSON.stringify(statusFile, null, 2)}\n`, "utf8");
  await writeFile(
    join(EVIDENCE_ROOT, "production-smoke-run.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
    "utf8",
  );

  if (summary.status === "PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK") {
    process.stdout.write(`PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK ${summary.subject_phase}\n`);
  } else {
    process.stdout.write(`BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK ${summary.risks.length}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
