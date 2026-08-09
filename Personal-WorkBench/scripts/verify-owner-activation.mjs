import { existsSync, readFileSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EVIDENCE_ROOT = join(ROOT, "13_evidence");
const TEST_EVIDENCE_FILE = process.env.NODE_ENV === "test" ? process.env.OWNER_ACTIVATION_EVIDENCE_FILE : null;
const EVIDENCE_FILE = TEST_EVIDENCE_FILE
  ? resolve(TEST_EVIDENCE_FILE)
  : join(EVIDENCE_ROOT, "owner_activation.json");
const TASKPACK_DEFAULT_PATH = resolve(
  process.env.HOME ?? "/tmp",
  "Downloads",
  "TaskPack",
  "Personal-WorkBench",
  "胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8",
);

const REQUIRED_ENV_KEYS = [
  "BETTER_AUTH_SECRET",
  "APP_ORIGIN",
  "GOOGLE_CLIENT_ID",
  "GOOGLE_CLIENT_SECRET",
  "TURNSTILE_SITE_KEY",
  "TURNSTILE_SECRET_KEY",
  "LEGAL_OPERATOR_NAME",
  "PRIVACY_CONTACT_EMAIL",
];

const MAIL_PROVIDER_KEYS = ["RESEND_API_KEY", "NITROSEND_API_KEY"];

function resolveTaskpackRoot() {
  const envRoot = process.env.TASKPACK_ROOT;
  const candidates = [envRoot, TASKPACK_DEFAULT_PATH].filter(Boolean);
  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    return resolve(candidate);
  }
  return null;
}

function runCommand(name, command, args, options = {}) {
  const child = spawnSync(command, args, {
    cwd: options.cwd || ROOT,
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${options.pathPrefix ? `${options.pathPrefix}:` : ""}${process.env.PATH || ""}`,
    },
    timeout: options.timeoutMs ?? 90_000,
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

function parseJsonText(text, context = "json") {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (error) {
    return { parseError: `${context}: ${error.message}` };
  }
}

function readEvidence(path) {
  if (!existsSync(path)) {
    return { exists: false, status: "MISSING", path };
  }

  try {
    const raw = JSON.parse(readFileSync(path, "utf8"));
    return {
      exists: true,
      path,
      status: raw.status || raw.current_state || "UNKNOWN",
      raw,
    };
  } catch (error) {
    return {
      exists: true,
      path,
      status: "INVALID_JSON",
      error: error.message,
    };
  }
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

function isValidOrigin(value) {
  if (!isNonEmptyString(value)) return false;
  try {
    const parsed = new URL(value);
    if (parsed.pathname !== "/") return false;
    if (parsed.protocol !== "https:") return false;
    return true;
  } catch {
    return false;
  }
}

function isLikelyEmail(value) {
  return isNonEmptyString(value) && /@/.test(value) && value.includes(".");
}

/**
 * Resend remains the taskpack default. NitroSend is only accepted when it is
 * explicitly selected and the runtime's narrow MailPort can receive its API
 * key. This summary is presence-only by design.
 */
export function resolveMailProvider(env = process.env) {
  const resendPresent = isNonEmptyString(env.RESEND_API_KEY);
  const nitrosendPresent = isNonEmptyString(env.NITROSEND_API_KEY);
  const requestedRaw = env.MAIL_PROVIDER?.trim().toLowerCase();
  const requested = requestedRaw || "default";

  if (requestedRaw && requestedRaw !== "resend" && requestedRaw !== "nitrosend") {
    return {
      requested: "invalid",
      selected: "missing",
      present: false,
      key_name: null,
      keys: {
        RESEND_API_KEY: resendPresent,
        NITROSEND_API_KEY: nitrosendPresent,
      },
    };
  }

  if (requestedRaw === "nitrosend") {
    return {
      requested,
      selected: nitrosendPresent ? "nitrosend" : "missing",
      present: nitrosendPresent,
      key_name: nitrosendPresent ? "NITROSEND_API_KEY" : null,
      keys: {
        RESEND_API_KEY: resendPresent,
        NITROSEND_API_KEY: nitrosendPresent,
      },
    };
  }

  if (requestedRaw === "resend") {
    return {
      requested,
      selected: resendPresent ? "resend" : "missing",
      present: resendPresent,
      key_name: resendPresent ? "RESEND_API_KEY" : null,
      keys: {
        RESEND_API_KEY: resendPresent,
        NITROSEND_API_KEY: nitrosendPresent,
      },
    };
  }

  return {
    requested,
    selected: resendPresent ? "resend" : "missing",
    present: resendPresent,
    key_name: resendPresent ? "RESEND_API_KEY" : null,
    keys: {
      RESEND_API_KEY: resendPresent,
      NITROSEND_API_KEY: nitrosendPresent,
    },
  };
}

/**
 * Evidence may prove that a value is configured, but must never preserve a
 * secret, a personal email address, or even a reversible value fragment.
 */
export function presenceOnly(value) {
  return { present: isNonEmptyString(value) };
}

/**
 * CLI responses can contain account identifiers or diagnostics that are not
 * suitable for a repository evidence file. Keep only execution metadata.
 */
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

export function redactCommandCheck(result) {
  return {
    status: result.status,
    ok: result.ok,
    output_redacted: Boolean(result.stdout || result.stderr),
  };
}

export function evidenceReference(evidence, source) {
  return {
    source,
    exists: evidence?.exists === true,
    status: evidence?.status ?? "UNKNOWN",
  };
}

function readWranglerConfigState() {
  const wranglerConfigPath = resolve(process.env.HOME || "", "Library", "Preferences", ".wrangler", "config", "default.toml");
  const evidencePath = "~/.wrangler/config/default.toml";
  if (!existsSync(wranglerConfigPath)) {
    return {
      exists: false,
      path: evidencePath,
      expired: true,
      has_token: false,
      reason: "wrangler 配置文件不存在",
    };
  }
  const content = readFileSync(wranglerConfigPath, "utf8");
  const tokenMatch = /oauth_token\s*=\s*"([^"]+)"/.exec(content);
  const expiresMatch = /expiration_time\s*=\s*"([^"]+)"/.exec(content);
  const refreshMatch = /refresh_token\s*=\s*"([^"]+)"/.exec(content);
  const expirationRaw = expiresMatch?.[1] ?? "";
  const expirationAt = expirationRaw ? new Date(expirationRaw) : null;
  const now = new Date();
  const isExpired = !expirationRaw || Number.isNaN(expirationAt?.getTime?.()) ? null : expirationAt.getTime() < now.getTime();
  return {
    exists: true,
    path: evidencePath,
    has_token: Boolean(tokenMatch?.[1]),
    has_refresh_token: Boolean(refreshMatch?.[1]),
    expiration_present: Boolean(expirationRaw),
    expired: isExpired,
  };
}

function getPrivacyConstants() {
  const sourcePath = join(ROOT, "server", "data", "account-lifecycle.ts");
  if (!existsSync(sourcePath)) return {};
  const source = readFileSync(sourcePath, "utf8");
  const policyMatch = /ACCOUNT_PRIVACY_POLICY_VERSION\s*=\s*"([^"]+)"/.exec(source);
  const hashMatch = /ACCOUNT_PRIVACY_NOTICE_SHA256\s*=\s*"([^"]+)"/.exec(source);
  return {
    policyVersion: policyMatch?.[1] ?? null,
    noticeHash: hashMatch?.[1] ?? null,
  };
}

async function fetchPagesProjectsWithCloudflareApi() {
  const token = process.env.CLOUDFLARE_API_TOKEN;
  const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
  if (!isNonEmptyString(token) || !isNonEmptyString(accountId)) {
    return {
      status: 0,
      ok: false,
      stderr: "缺少 CLOUDFLARE_API_TOKEN 或 CLOUDFLARE_ACCOUNT_ID，无法通过 Cloudflare API 直接校验 Pages。",
      json: null,
      raw: "",
    };
  }

  const endpoint = `https://api.cloudflare.com/client/v4/accounts/${encodeURIComponent(accountId)}/pages/projects`;
  try {
    const response = await fetch(endpoint, {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });
    const raw = await response.text();
    const json = parseJsonText(raw, "Cloudflare API pages project list");
    const success = response.ok && json && json.success === true;
    if (!response.ok) {
      return {
        status: response.status,
        ok: false,
        stderr: `Cloudflare API 响应异常：HTTP ${response.status}`,
        json: json,
        raw,
      };
    }

    return {
      status: response.status,
      ok: success,
      stderr: success ? null : `Cloudflare API 返回 success=false：${JSON.stringify(json?.errors || [])}`,
      json: success ? json : null,
      raw,
    };
  } catch (error) {
    return {
      status: 0,
      ok: false,
      stderr: `Cloudflare API 调用失败：${error.message}`,
      json: null,
      raw: "",
    };
  }
}

async function main() {
  const taskpackRoot = resolveTaskpackRoot();
  const runAt = new Date().toISOString();
  const summary = {
    schema_version: "2.0.0",
    subject_phase: "S5-T2",
    status: null,
    verdict: "NOT_ISSUED_PRE_VERIFIER",
    runAt,
    generated_at: runAt,
    environment: {
      taskpack_available: Boolean(taskpackRoot),
      configuration_source: "local_environment_presence_only",
      app_origin_present: isNonEmptyString(process.env.APP_ORIGIN),
      app_origin_valid_https: isValidOrigin(process.env.APP_ORIGIN),
    },
    command_results: [],
    checks: {
      required_secrets: {
      },
      wrangler: {
        whoami: null,
        pages_project_list: null,
        auth_channel: "NONE",
        auth_mode: "SKIP",
        auth_recovery_hint: null,
        config: null,
      },
      owner_approval: null,
      asset_rights: null,
      callbacks: null,
      privacy_gate: null,
      sites_shape: null,
      sites_bindings_contract: null,
      release_verifier: null,
      saved_version: null,
    },
    evidence: {
      owner_approval: readEvidence(taskpackRoot ? join(taskpackRoot, "OWNER_APPROVAL.json") : "OWNER_APPROVAL.json"),
      sites_bindings_contract: readEvidence(taskpackRoot ? join(taskpackRoot, "10_deployment", "SITES_BINDINGS_CONTRACT.json") : "NOT_FOUND"),
      asset_manifest: readEvidence(join(ROOT, "13_evidence", "asset_manifest.json")),
      release_verifier: readEvidence(join(ROOT, "13_evidence", "verifier.json")),
      saved_version: readEvidence(join(ROOT, "13_evidence", "saved_version.json")),
      env_privacy_constants: getPrivacyConstants(),
    },
    risks: [],
    next_steps: [],
  };

  const wranglerConfig = readWranglerConfigState();
  summary.checks.wrangler.config = wranglerConfig;
  const hasCloudflareApiToken = isNonEmptyString(process.env.CLOUDFLARE_API_TOKEN);
  if (!taskpackRoot) {
    summary.risks.push(
      "未找到任务包根目录，无法对 OWNER_APPROVAL、项目绑定清单和生产前置合同做一致性对照；请设置 TASKPACK_ROOT 后重跑。",
    );
  }
  if (!wranglerConfig.has_token && !hasCloudflareApiToken) {
    summary.risks.push(
      `未检测到 wrangler oauth_token：请执行 ` +
      "`npx wrangler logout` 后再 `npx wrangler login` 重新完成授权，当前配置路径：" +
      ` ${wranglerConfig.path}`,
    );
  } else if (wranglerConfig.expired === true && !hasCloudflareApiToken) {
    summary.risks.push("wrangler 本地 token 已过期；请执行 `npx wrangler logout` 后 `npx wrangler login` 重新登录并重试。");
  } else if (wranglerConfig.expired === null && !hasCloudflareApiToken) {
    summary.risks.push("无法解析 wrangler default.toml 中的 expiration_time，建议执行 `npx wrangler login` 后重试。");
  }

  const mailFrom = process.env.MAIL_FROM ?? "";
  const authFromEmail = process.env.AUTH_FROM_EMAIL ?? "";
  const mailProvider = resolveMailProvider();
  const requiredMailSource = {
    source: "missing",
    present: {
      MAIL_FROM: isNonEmptyString(mailFrom),
      AUTH_FROM_EMAIL: isNonEmptyString(authFromEmail),
    },
  };
  for (const key of REQUIRED_ENV_KEYS) {
    const value = process.env[key] ?? "";
    const item = presenceOnly(value);
    summary.checks.required_secrets[key] = item;
    if (!item.present) {
      summary.risks.push(`缺少环境值：${key}`);
    }
  }
  for (const key of MAIL_PROVIDER_KEYS) {
    summary.checks.required_secrets[key] = presenceOnly(process.env[key] ?? "");
  }
  summary.checks.required_secrets.TRANSACTIONAL_MAIL_PROVIDER = mailProvider;
  if (!mailProvider.present) {
    summary.risks.push("缺少事务邮件凭据：需要 RESEND_API_KEY，或显式选择 NitroSend 后提供 NITROSEND_API_KEY。");
  }

  if (!requiredMailSource.present.MAIL_FROM && !requiredMailSource.present.AUTH_FROM_EMAIL) {
    summary.risks.push("缺少邮件发送发件人：MAIL_FROM（任务包要求）与 AUTH_FROM_EMAIL（运行时要求）均未配置");
    requiredMailSource.source = "missing";
  } else if (requiredMailSource.present.AUTH_FROM_EMAIL) {
    requiredMailSource.source = "AUTH_FROM_EMAIL";
  } else {
    requiredMailSource.source = "MAIL_FROM";
  }
  summary.checks.required_secrets.MAIL_FROM_FROM_RUNTIME = requiredMailSource;

  const originIsValid = isValidOrigin(process.env.APP_ORIGIN);
  const hasAuthRoute = existsSync(join(ROOT, "app", "api", "auth", "[...all]", "route.ts"));
  summary.checks.callbacks = {
    app_origin_present: isNonEmptyString(process.env.APP_ORIGIN),
    app_origin_valid_https: originIsValid,
    expected_callback_path: "/api/auth/callback/google",
    expected_callback_constructed: originIsValid,
    auth_callback_route_present: hasAuthRoute,
    callback_platform_register_verification: "NOT_VERIFIED_LOCALLY",
  };
  if (!originIsValid) {
    summary.risks.push("APP_ORIGIN 无效：必须是 HTTPS origin（生产环境）");
  }
  if (!hasAuthRoute) {
    summary.risks.push("未检测到 app/api/auth/[...all]/route.ts；无法确认 Google callback 路由可达。");
  }

  const hostingPath = join(ROOT, ".openai", "hosting.json");
  const hostingEvidence = readEvidence(hostingPath);
  summary.evidence.sites_shape = hostingEvidence;
  if (!hostingEvidence.exists) {
    summary.risks.push("缺少 .openai/hosting.json，无法确认项目 project_id 与 D1/R2 绑定是否与 Sites 项目一致。");
  } else if (typeof hostingEvidence.raw?.project_id !== "string" || !hostingEvidence.raw.project_id) {
    summary.risks.push(".openai/hosting.json 中 project_id 缺失或不可解析。");
  } else {
    summary.checks.sites_shape = {
      project_id: hostingEvidence.raw.project_id,
      d1: hostingEvidence.raw.d1,
      r2: hostingEvidence.raw.r2,
      reused_projectevidence: false,
    };
  }

  const bindingContract = summary.evidence.sites_bindings_contract;
  if (!bindingContract.exists) {
    summary.risks.push("未读取到 10_deployment/SITES_BINDINGS_CONTRACT.json；无法核对生产绑定合同。");
    summary.checks.sites_bindings_contract = {
      exists: false,
      project_policy: null,
      d1_match: null,
      r2_match: null,
      expected_secret_keys: null,
      present_secret_keys: null,
      hosting_json_after_provision: null,
      project_id_contract: null,
    };
  } else {
    const raw = bindingContract.raw || {};
    const expectedSecretKeys = Array.isArray(raw.secret_keys) ? raw.secret_keys : [];
    const hasMailSender = requiredMailSource.source !== "missing";
    const presentSecretKeys = expectedSecretKeys.filter((key) => {
      if (key === "MAIL_FROM") return hasMailSender;
      if (key === "RESEND_API_KEY") return mailProvider.keys.RESEND_API_KEY;
      return isNonEmptyString(process.env[key]);
    });

    summary.checks.sites_bindings_contract = {
      exists: true,
      project_policy: raw.site_project_policy || null,
      forbidden_project_reuse: raw.forbidden_project_reuse || null,
      d1_match: summary.checks.sites_shape?.d1 === raw.hosting_json_after_provision?.d1,
      r2_match: summary.checks.sites_shape?.r2 === raw.hosting_json_after_provision?.r2,
      project_id_match: null,
      project_id_note: null,
      expected_secret_keys: expectedSecretKeys,
      present_secret_keys: presentSecretKeys,
      mail_provider_binding: {
        taskpack_default_key: expectedSecretKeys.includes("RESEND_API_KEY") ? "RESEND_API_KEY" : null,
        selected_provider: mailProvider.selected,
        active_runtime_key: mailProvider.key_name,
        compatible_mailport_present: mailProvider.present,
      },
      hosting_json_after_provision: raw.hosting_json_after_provision || null,
      project_id_contract: raw.hosting_json_after_provision?.project_id || null,
    };

    if (isNonEmptyString(raw.site_project_policy) && raw.site_project_policy !== "create_new_isolated_project") {
      summary.risks.push(`SITES_BINDINGS_CONTRACT.site_project_policy 非预期值：${raw.site_project_policy}`);
    }
    const contractProjectId = raw.hosting_json_after_provision?.project_id || null;
    const actualProjectId = summary.checks.sites_shape?.project_id || null;
    const isPlaceholderProjectId =
      typeof contractProjectId === "string" && contractProjectId.includes("generated_by_sites_and_never_hand_invented");
    if (contractProjectId) {
      summary.checks.sites_bindings_contract.project_id_match = isPlaceholderProjectId ? null : actualProjectId === contractProjectId;
      summary.checks.sites_bindings_contract.project_id_note = isPlaceholderProjectId
        ? "契约中的 project_id 使用占位标识，需在项目正式 provision 后由生产配置确认"
        : actualProjectId === contractProjectId
          ? "matches contract"
          : `project_id 不一致：contract=${contractProjectId}，当前=${actualProjectId || "MISSING"}`;
      if (!isPlaceholderProjectId && actualProjectId !== contractProjectId) {
        summary.risks.push(
          `Sites project_id 不一致：SITES_BINDINGS_CONTRACT=${contractProjectId}, 当前配置=${actualProjectId || "MISSING"}`,
        );
      }
    }
    if (raw.hosting_json_after_provision?.d1 && summary.checks.sites_shape?.d1 !== raw.hosting_json_after_provision?.d1) {
      summary.risks.push(
        `D1 绑定不一致：SITES_BINDINGS_CONTRACT=${raw.hosting_json_after_provision?.d1 || "MISSING"}, 当前配置=${summary.checks.sites_shape?.d1 || "MISSING"}`,
      );
    }
    if (raw.hosting_json_after_provision?.r2 && summary.checks.sites_shape?.r2 !== raw.hosting_json_after_provision?.r2) {
      summary.risks.push(
        `R2 绑定不一致：SITES_BINDINGS_CONTRACT=${raw.hosting_json_after_provision?.r2 || "MISSING"}, 当前配置=${summary.checks.sites_shape?.r2 || "MISSING"}`,
      );
    }
    if (expectedSecretKeys.length > 0) {
      const missingContractSecrets = expectedSecretKeys.filter((key) => {
        if (key === "MAIL_FROM") return !hasMailSender;
        if (key === "RESEND_API_KEY") return !mailProvider.present;
        return !isNonEmptyString(process.env[key]);
      });
      if (missingContractSecrets.length > 0) {
        summary.risks.push(`SITES_BINDINGS_CONTRACT 约定密钥未完整配置到环境：${missingContractSecrets.join(", ")}`);
      }
    }
  }

  const privacy = summary.evidence.owner_approval;
  const ownerApproved = privacy.exists && privacy.raw?.owner_decision === "APPROVED";
  summary.checks.owner_approval = {
    exists: privacy.exists,
    owner_decision: privacy.raw?.owner_decision ?? null,
      production_side_effect_authorization: privacy.raw?.production_side_effect_authorization ?? null,
    };
  if (!privacy.exists || privacy.raw === null) {
    summary.risks.push("无法读取 OWNER_APPROVAL.json。");
  } else {
    if (!ownerApproved) {
      summary.risks.push("OWNER_APPROVAL 未 APPROVED。");
    }
    if (!privacy.raw.production_side_effect_authorization) {
      summary.risks.push("OWNER_APPROVAL.production_side_effect_authorization 为 false：当前不允许生产副作用推进。");
    }
  }

  const releaseVerifier = summary.evidence.release_verifier;
  summary.checks.release_verifier = {
    exists: releaseVerifier.exists,
    status: releaseVerifier.status,
    phase: releaseVerifier.raw?.subject_phase || null,
  };
  if (!releaseVerifier.exists) {
    summary.risks.push("未生成 13_evidence/verifier.json；缺少本地 release 冻结准备证据。");
  } else if (releaseVerifier.raw?.status !== "PASS_BUILD_LAST_MILE_READINESS") {
    summary.risks.push(`13_evidence/verifier.json 当前状态为 ${releaseVerifier.status}，未达到 PASS_BUILD_LAST_MILE_READINESS。`);
  }

  const savedVersion = summary.evidence.saved_version;
  const savedVersionRaw = savedVersion.raw || {};
  const savedVersionReadback = savedVersionRaw.post_save_readback || {};
  const savedVersionIdentity = savedVersionRaw.sites_saved_version || {};
  const savedVersionPrivate =
    savedVersionReadback.access_mode === "custom" &&
    savedVersionReadback.allowed_users_count === 1 &&
    savedVersionReadback.allowed_groups_count === 0 &&
    savedVersionReadback.external_visitor_count === 0;
  const savedVersionNotDeployed =
    savedVersionReadback.deployed === false &&
    savedVersionReadback.live_url_present === false &&
    savedVersionReadback.preview_url_present === false;
  const savedVersionIdentityPresent =
    typeof savedVersionIdentity.source_commit === "string" &&
    savedVersionIdentity.source_commit.length === 40 &&
    Number.isInteger(savedVersionIdentity.version_number) &&
    savedVersionIdentity.version_number > 0;
  const savedVersionProjectMatchesHosting =
    typeof savedVersionIdentity.project_id === "string" &&
    savedVersionIdentity.project_id === summary.checks.sites_shape?.project_id;
  summary.checks.saved_version = {
    exists: savedVersion.exists,
    status: savedVersion.status,
    source_identity_present: savedVersionIdentityPresent,
    project_id_matches_hosting: savedVersionProjectMatchesHosting,
    private_access_readback: savedVersionPrivate,
    no_deployment_readback: savedVersionNotDeployed,
  };
  const savedVersionOk =
    savedVersion.exists &&
    savedVersion.status === "PASS_PRIVATE_SAVED_VERSION_CANDIDATE" &&
    savedVersionIdentityPresent &&
    savedVersionProjectMatchesHosting &&
    savedVersionPrivate &&
    savedVersionNotDeployed;
  if (!savedVersionOk) {
    summary.risks.push("缺少可验证的私有 Saved Version：需先完成 source/version 绑定、私有访问与无部署回读。");
  }

  const privacyPolicyEnv = process.env.PRIVACY_POLICY_VERSION;
  const privacyNoticeEnv = process.env.PRIVACY_NOTICE_SHA256;
  const constPrivacy = summary.evidence.env_privacy_constants;
  const hasPolicyVersion = isNonEmptyString(privacyPolicyEnv) && isNonEmptyString(privacyNoticeEnv);
  summary.checks.privacy_gate = {
    privacy_policy_version_present: isNonEmptyString(privacyPolicyEnv),
    privacy_notice_hash_present: isNonEmptyString(privacyNoticeEnv),
    privacy_policy_version_match: constPrivacy.policyVersion ? privacyPolicyEnv === constPrivacy.policyVersion : false,
    privacy_notice_hash_match: constPrivacy.noticeHash ? privacyNoticeEnv === constPrivacy.noticeHash : false,
    legal_operator_name_present: isNonEmptyString(process.env.LEGAL_OPERATOR_NAME),
    privacy_contact_email_present: isLikelyEmail(process.env.PRIVACY_CONTACT_EMAIL),
  };
  if (!summary.checks.privacy_gate.legal_operator_name_present) {
    summary.risks.push("缺少运营者名称（LEGAL_OPERATOR_NAME）。");
  }
  if (!summary.checks.privacy_gate.privacy_contact_email_present) {
    summary.risks.push("缺少隐私联系邮箱（PRIVACY_CONTACT_EMAIL）。");
  }
  if (!hasPolicyVersion) {
    summary.risks.push("缺少隐私声明环境值：PRIVACY_POLICY_VERSION 或 PRIVACY_NOTICE_SHA256。");
  } else {
    if (!summary.checks.privacy_gate.privacy_policy_version_match) {
      summary.risks.push("PRIVACY_POLICY_VERSION 与仓库内当前隐私版本不一致。");
    }
    if (!summary.checks.privacy_gate.privacy_notice_hash_match) {
      summary.risks.push("PRIVACY_NOTICE_SHA256 与仓库内当前版本哈希不一致。");
    }
  }

  const assetStatus = summary.evidence.asset_manifest;
  const authorizedAssetRecord = assetStatus.raw?.authorized_public_assets;
  const attestationComplete =
    assetStatus.status === "PASS_FINAL_AUTHORIZED_ASSETS" &&
    assetStatus.raw?.public_release_policy?.current_state === "APPROVED" &&
    assetStatus.raw?.public_release_policy?.authorization_scope === "NONCOMMERCIAL_PUBLIC_WEBSITE_ONLY" &&
    isNonEmptyString(authorizedAssetRecord?.authorization_record) &&
    authorizedAssetRecord?.asset_count === 37 &&
    /^[a-f0-9]{64}$/.test(authorizedAssetRecord?.asset_set_sha256 ?? "") &&
    authorizedAssetRecord?.same_container_paths_verified === true &&
    authorizedAssetRecord?.independent_legal_verification === "NOT_PERFORMED";
  if (!assetStatus.exists) {
    summary.risks.push("未生成资产清单，无法确认公开素材权利是否已通过。");
  } else if (assetStatus.status === "PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED") {
    summary.risks.push(
      "asset_manifest 当前状态为 PUBLIC_DEPLOY_BLOCKED：公开授权素材权利和最终素材替换尚未提交。必须阻断本地预检通过。"
    );
  } else if (assetStatus.raw?.public_release_policy?.current_state !== "APPROVED") {
    summary.risks.push(`资产公开状态不是 APPROVED：${assetStatus.raw?.public_release_policy?.current_state || "UNKNOWN"}。`);
  } else if (!attestationComplete) {
    summary.risks.push("资产公开状态虽为 APPROVED，但缺少非商业授权记录、精确素材哈希或同容器绑定，不能视为可验证的公开素材证据。");
  }
  summary.checks.asset_rights = {
    status: assetStatus.status,
    current_state: assetStatus.raw?.public_release_policy?.current_state ?? null,
    owner_declaration_present: isNonEmptyString(assetStatus.raw?.public_release_policy?.owner_declaration),
    authorization_scope: assetStatus.raw?.public_release_policy?.authorization_scope ?? null,
    attestation_record_present: isNonEmptyString(authorizedAssetRecord?.authorization_record),
    attested_asset_count: authorizedAssetRecord?.asset_count ?? null,
    attested_asset_set_hash_present: /^[a-f0-9]{64}$/.test(authorizedAssetRecord?.asset_set_sha256 ?? ""),
    same_container_paths_verified: authorizedAssetRecord?.same_container_paths_verified === true,
    independent_legal_verification: authorizedAssetRecord?.independent_legal_verification ?? null,
    attestation_complete: attestationComplete,
  };

  const canRunWranglerWhoami =
    hasCloudflareApiToken ||
    (wranglerConfig.exists && wranglerConfig.has_token);
  summary.checks.wrangler.auth_channel = canRunWranglerWhoami
    ? hasCloudflareApiToken
      ? "CLOUDFLARE_API_TOKEN"
      : wranglerConfig.has_token
        ? "LOCAL_TOKEN"
        : "NONE"
    : "NONE";
  summary.checks.wrangler.auth_mode = canRunWranglerWhoami
    ? hasCloudflareApiToken
      ? "CLOUDFLARE_API_TOKEN"
      : "LOCAL_TOKEN"
    : "SKIP";
  if (!canRunWranglerWhoami) {
    const wranglerConfigReason =
      !wranglerConfig.exists ||
      !wranglerConfig.has_token ||
      wranglerConfig.expired === true ||
      wranglerConfig.expired === null
        ? "wrangler 配置缺失/异常，请先完成 wrangler 登录与 token 检查"
        : "wrangler 配置不可用于认证";
    summary.checks.wrangler.whoami = {
      status: null,
      ok: false,
      skipped: true,
      reason: wranglerConfigReason,
      output_redacted: false,
      auth_recovery_hint:
        "检测到 wrangler 配置不满足认证要求：建议执行 `npx wrangler logout && npx wrangler login`，或在非交互场景设置 CLOUDFLARE_API_TOKEN",
    };
    summary.checks.wrangler.auth_recovery_hint = summary.checks.wrangler.whoami.auth_recovery_hint;
    summary.checks.wrangler.pages_project_list = {
      status: null,
      ok: false,
      skipped: true,
      reason: "已跳过 wrangler pages project list：认证条件未满足",
      output_redacted: false,
    };
  } else {
    const whoami = runCommand("wrangler whoami", "npx", ["wrangler", "whoami", "--json"], {
      pathPrefix: join(ROOT, "node_modules", ".bin"),
      timeoutMs: 45_000,
    });
    summary.command_results.push(redactCommandResult(whoami));
    const whoamiText = `${whoami.stderr || ""} ${whoami.stdout || ""}`.toLowerCase();
    const wranglerAuthLikelyStale =
      !whoami.ok &&
      (whoamiText.includes("failed to fetch auth token") ||
        whoamiText.includes("not logged in") ||
        whoamiText.includes("invalid") ||
        whoamiText.includes("400"));
    const nonInteractiveApiTokenHint = whoamiText.includes("necessary to set a cloudflare_api_token");
    const invalidApiTokenHint = hasCloudflareApiToken && (whoamiText.includes("6111") || whoamiText.includes("invalid request headers"));
    const wranglerAuthRecoveryHint = invalidApiTokenHint
      ? "检测到 CLOUDFLARE_API_TOKEN 无效（Authorization 头格式/权限异常）；请重置并设置可用于 Pages 的有效 token"
      : wranglerAuthLikelyStale
      ? "检测到 wrangler 认证态疑似失效/未登录：建议执行 `npx wrangler logout && npx wrangler login` 后重试"
      : nonInteractiveApiTokenHint
        ? "当前环境为非交互执行，请设置 CLOUDFLARE_API_TOKEN 后重试 wrangler 命令"
        : null;
    summary.checks.wrangler.whoami = {
      ...redactCommandCheck(whoami),
      auth_recovery_hint: wranglerAuthRecoveryHint,
    };
    summary.checks.wrangler.auth_recovery_hint = summary.checks.wrangler.whoami.auth_recovery_hint;

    if (!whoami.ok) {
      let didFallbackPagesCheck = false;
      if (hasCloudflareApiToken) {
        const apiProjectList = await fetchPagesProjectsWithCloudflareApi();
        const list = apiProjectList.json && Array.isArray(apiProjectList.json.result) ? apiProjectList.json.result : [];
        summary.checks.wrangler.pages_project_list = {
          status: apiProjectList.status,
          ok: apiProjectList.ok,
          result_count: apiProjectList.ok ? list.length : null,
          output_redacted: Boolean(apiProjectList.raw || apiProjectList.stderr),
        };
        didFallbackPagesCheck = apiProjectList.ok;
        const projectId = summary.evidence.sites_shape?.raw?.project_id || null;
      const contractProjectId = summary.checks.sites_bindings_contract?.project_id_contract || null;
      const isProjectIdMatchRequired =
        contractProjectId &&
        !String(contractProjectId).includes("generated_by_sites_and_never_hand_invented");

      if (apiProjectList.ok && projectId && isProjectIdMatchRequired) {
        const matched = list.some((entry) =>
          entry?.id === projectId || entry?.name === projectId || entry?.project_id === projectId,
        );
        if (!matched) {
          summary.risks.push(`无法在 Cloudflare API 的 Pages project list 中发现 project_id=${projectId}，或本账号未绑定该项目。`);
        }
      } else if (!projectId) {
        summary.risks.push("未读取到 .openai/hosting.json project_id，不能做 Sites project 交叉核验。");
      }
        if (!apiProjectList.ok) {
          summary.risks.push(
            "wrangler whoami 失败，且 CLOUDFLARE_API_TOKEN 未能成功查询 Pages project list；请检查 token 权限或改为 OAuth 登录。",
          );
        }
      } else {
        summary.checks.wrangler.pages_project_list = {
          status: null,
          ok: false,
          skipped: true,
          reason: "已跳过 wrangler pages project list：未通过 wrangler 身份认证且未设置 CLOUDFLARE_API_TOKEN。",
          output_redacted: false,
        };
        summary.risks.push(
          "未通过 wrangler 身份认证（wrangler whoami 失败）；无法在当前上下文确认 Sites 控制面可访问。"
            + (wranglerAuthLikelyStale
              ? " 建议先执行 `npx wrangler logout`，再执行 `npx wrangler login` 并重试。"
              : ""),
        );
      }

      if (!didFallbackPagesCheck) {
        summary.risks.push(
          "未通过 wrangler 身份认证（wrangler whoami 失败）；无法在当前上下文确认 Sites 控制面可访问。",
        );
      }
    } else {
      const parsedWhoami = parseJsonText(whoami.stdout, "wrangler whoami");
      if (!parsedWhoami) {
        summary.risks.push("wrangler whoami 可执行但返回不可解析 JSON。");
      }

      const projectList = runCommand(
        "wrangler pages project list",
        "npx",
        ["wrangler", "pages", "project", "list", "--json"],
        { pathPrefix: join(ROOT, "node_modules", ".bin"), timeoutMs: 60_000 },
      );
      summary.command_results.push(redactCommandResult(projectList));
      summary.checks.wrangler.pages_project_list = redactCommandCheck(projectList);
      const projectListJson = parseJsonText(projectList.stdout, "wrangler pages project list");
      const projectId = summary.evidence.sites_shape?.raw?.project_id || null;
      if (!projectList.ok) {
        summary.risks.push("wrangler pages project list 失败：无法核验本地 project_id 的 Sites 读写权限。");
      } else if (!projectId) {
        summary.risks.push("未读取到 .openai/hosting.json project_id，不能做 Sites project 交叉核验。");
      } else {
        const list = Array.isArray(projectListJson)
          ? projectListJson
          : Array.isArray(projectListJson?.result)
            ? projectListJson.result
            : [];
        const contractProjectId = summary.checks.sites_bindings_contract?.project_id_contract || null;
        const isProjectIdMatchRequired =
          contractProjectId &&
          !String(contractProjectId).includes("generated_by_sites_and_never_hand_invented");
        const matched = list.some((entry) =>
          entry?.id === projectId || entry?.name === projectId || entry?.project_id === projectId,
        );
        if (!matched && isProjectIdMatchRequired) {
          summary.risks.push(`无法在 Sites project list 中发现 project_id=${projectId}，或本账号未绑定该项目。`);
        }
      }
    }
  }

  const requiredMail = requiredMailSource.source !== "missing";
  const envAliasValidated =
    isLikelyEmail(authFromEmail || mailFrom);
  const originChecked = isValidOrigin(process.env.APP_ORIGIN ?? "");
  const callbacksReady = summary.checks.callbacks?.auth_callback_route_present;
  const secretsOk = REQUIRED_ENV_KEYS.every((key) => {
    if (key === "LEGAL_OPERATOR_NAME" || key === "PRIVACY_CONTACT_EMAIL") return true;
    if (key === "PRIVACY_NOTICE_SHA256" || key === "PRIVACY_POLICY_VERSION") return true;
    if (key === "MAIL_FROM") return requiredMail;
    return summary.checks.required_secrets[key]?.present;
  }) && mailProvider.present;

  const privacyGateOk =
    summary.checks.privacy_gate?.legal_operator_name_present &&
    summary.checks.privacy_gate?.privacy_contact_email_present &&
    summary.checks.privacy_gate?.privacy_policy_version_match &&
    summary.checks.privacy_gate?.privacy_notice_hash_match;

  const wranglerRecoveryHint = summary.checks.wrangler.auth_recovery_hint;

  const ownerOk =
    summary.checks.owner_approval.owner_decision === "APPROVED" &&
    summary.checks.owner_approval.production_side_effect_authorization === true;
  const assetOk = summary.checks.asset_rights?.status === "PASS_FINAL_AUTHORIZED_ASSETS" &&
    summary.checks.asset_rights?.current_state === "APPROVED" &&
    summary.checks.asset_rights?.attestation_complete === true;

  const callbackOk =
    originChecked && callbacksReady && summary.checks.callbacks?.expected_callback_constructed === true;

  const wranglerOk = summary.checks.wrangler.auth_mode === "LOCAL_TOKEN"
    ? summary.checks.wrangler.whoami.ok
    : summary.checks.wrangler.whoami.ok || summary.checks.wrangler.pages_project_list?.ok;
  const projectMatched = summary.checks.wrangler.pages_project_list?.ok;
  const bindingContractOk = summary.checks.sites_bindings_contract?.exists === true && summary.checks.sites_bindings_contract?.d1_match === true
    && summary.checks.sites_bindings_contract?.r2_match === true;
  const releaseVerifierOk = summary.checks.release_verifier?.status === "PASS_BUILD_LAST_MILE_READINESS";
  if (
    secretsOk &&
    requiredMail &&
    envAliasValidated &&
    originChecked &&
    callbackOk &&
    wranglerOk &&
    projectMatched &&
    ownerOk &&
    assetOk &&
    privacyGateOk &&
    requiredMailSource.source !== "missing" &&
    bindingContractOk &&
    releaseVerifierOk &&
    savedVersionOk
  ) {
    summary.status = "PASS_LOCAL_OWNER_ACTIVATION_PRECHECK";
    summary.next_steps = [
      "已通过 Owner 激活本地预检：请在生产平台执行 Google/邮件/Turnstile 回调和发送域核验，随后执行 production smoke 与回滚演练。",
    "确认已上传最终获授权的公开素材后继续 S5-T2 实际发布门槛。",
    "执行 S5-T3 前更新 13_evidence/owner_activation.json 并重新确认 risks 全清。",
    "本次仅是本地预检；S5-T3 仍需独立 production evidence 与回滚验证。",
    "若 Owner 未继续授权，请按当前 risks 再次推进。",
    "建议在运行 OAuth 回调联调后记录平台凭证截图或平台审计 ID 以便后续可追溯。",
  ];
  } else {
    summary.status = "BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK";
    if (summary.risks.length === 0) {
      summary.risks.push("存在未分类阻断项，请补齐 Owner 激活前置。");
    }
    summary.next_steps = [
      "按 RUN_CONTRACT_S5_T2.md 逐项推进：先完成本地身份与证据口径齐套，再进入生产副作用授权。",
      wranglerRecoveryHint ??
        "执行 wrangler 登录与项目可见性校验：`npx wrangler whoami`、`npx wrangler pages project list --json`。",
      "将必需 Secrets（APP_ORIGIN、BETTER_AUTH_SECRET、GOOGLE_CLIENT_ID/SECRET、默认 RESEND_API_KEY 或显式 MAIL_PROVIDER=nitrosend + NITROSEND_API_KEY、TURNSTILE_SITE_KEY/SECRET_KEY、LEGAL_OPERATOR_NAME、PRIVACY_CONTACT_EMAIL、MAIL_FROM 或 AUTH_FROM_EMAIL）逐项补齐到 Sites Settings。",
      "完成 Google callback 验证、邮件发送域、Turnstile、隐私信息（运营者名/联系邮箱/版本哈希）与资产授权，确认 OWNER_APPROVAL.production_side_effect_authorization 为 true。",
      "确认 `.openai/hosting.json` 的 project_id 与 SITES_BINDINGS_CONTRACT.json 占位 `generated_by_sites_and_never_hand_invented` 差异在正式 provision 后核对一致。",
      "同步任务包《胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包》最新 OWNER_APPROVAL 与资产清单，补齐后重新运行 `npm run verify:owner-activation`。",
      "完成上述后只在 risks 清空且 next_steps 无阻断项时，方可进入 S5-T3。",
    ];
  }

  summary.evidence = {
    owner_approval: evidenceReference(summary.evidence.owner_approval, "taskpack/OWNER_APPROVAL.json"),
    sites_bindings_contract: evidenceReference(
      summary.evidence.sites_bindings_contract,
      "taskpack/10_deployment/SITES_BINDINGS_CONTRACT.json",
    ),
    asset_manifest: evidenceReference(summary.evidence.asset_manifest, "13_evidence/asset_manifest.json"),
    release_verifier: evidenceReference(summary.evidence.release_verifier, "13_evidence/verifier.json"),
    saved_version: evidenceReference(summary.evidence.saved_version, "13_evidence/saved_version.json"),
    env_privacy_constants: {
      policy_version_present: isNonEmptyString(summary.evidence.env_privacy_constants?.policyVersion),
      notice_hash_present: isNonEmptyString(summary.evidence.env_privacy_constants?.noticeHash),
    },
  };

  await mkdir(dirname(EVIDENCE_FILE), { recursive: true });
  await writeFile(EVIDENCE_FILE, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  if (summary.status === "PASS_LOCAL_OWNER_ACTIVATION_PRECHECK") {
    process.stdout.write(`PASS_LOCAL_OWNER_ACTIVATION_PRECHECK ${summary.subject_phase}\n`);
  } else {
    process.stdout.write(`BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK ${summary.risks.length}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
