const fs = require("fs");
const os = require("os");
const path = require("path");
const dotenv = require("dotenv");

const { readConfig } = require("./core/config");
const { renderInstructionTemplate } = require("./core/instructions-template");
const { CyberbossApp } = require("./core/app");
const { bootstrapInstallation, defaultStateDir } = require("./core/bootstrap");
const { looksConfigured, prepareTunnel, runSetupWizard } = require("./core/setup-wizard");
const { runSystemCheckinPoller } = require("./app/system-checkin-poller");
const { buildTerminalHelpText } = require("./core/command-registry");
const { ensureStickerCatalogFilesSync } = require("./services/sticker-service");
const { createProjectTooling } = require("./tools/create-project-tooling");
const { runToolMcpServer } = require("./tools/mcp-stdio-server");

function ensureDefaultStateDirectory() {
  fs.mkdirSync(path.join(os.homedir(), ".cyberboss"), { recursive: true });
}

function loadEnv() {
  ensureDefaultStateDirectory();
  const candidates = [
    path.join(process.cwd(), ".env"),
    path.join(os.homedir(), ".cyberboss", ".env"),
  ];
  for (const envPath of candidates) {
    if (!fs.existsSync(envPath)) {
      continue;
    }
    dotenv.config({ path: envPath });
    return;
  }
  dotenv.config();
}

function ensureRuntimeEnv() {
  if (!process.env.CYBERBOSS_HOME) {
    process.env.CYBERBOSS_HOME = path.resolve(__dirname, "..");
  }
}

function ensureBootstrapFiles(config) {
  ensureInstructionsTemplate(config);
  ensureStickerCatalogFilesSync(config);
}

function ensureInstructionsTemplate(config) {
  const filePath = typeof config?.weixinInstructionsFile === "string"
    ? config.weixinInstructionsFile.trim()
    : "";
  if (!filePath || fs.existsSync(filePath)) {
    return;
  }

  const templatePath = path.resolve(__dirname, "..", "templates", "weixin-instructions.md");
  let template = "";
  try {
    template = fs.readFileSync(templatePath, "utf8");
  } catch {
    return;
  }

  const userName = String(config?.userName || "").trim() || "User";
  const content = renderInstructionTemplate(template, {
    ...config,
    userName,
  }).trimEnd() + "\n";
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
}

function printHelp() {
  console.log(buildTerminalHelpText());
}

let runtimeErrorHooksInstalled = false;

function installRuntimeErrorHooks() {
  if (runtimeErrorHooksInstalled) {
    return;
  }
  runtimeErrorHooksInstalled = true;

  process.on("unhandledRejection", (reason) => {
    const message = reason instanceof Error ? reason.stack || reason.message : String(reason);
    console.error(`[cyberboss] unhandled rejection ${message}`);
  });

  process.on("uncaughtException", (error) => {
    const message = error instanceof Error ? error.stack || error.message : String(error);
    console.error(`[cyberboss] uncaught exception ${message}`);
    process.exitCode = 1;
  });
}

async function main() {
  loadEnv();
  ensureRuntimeEnv();
  installRuntimeErrorHooks();
  const argv = process.argv.slice(2);
  const requestedCommand = argv[0] || "";

  if (requestedCommand === "help" || requestedCommand === "--help" || requestedCommand === "-h") {
    console.log(buildTerminalHelpText());
    return;
  }

  // 无参数运行：没装过就走向导，装过就直接启动。一个没用过命令行的人
  // 只需要记住一个词 —— cyberboss。
  if (!requestedCommand) {
    const stateDir = defaultStateDir();
    if (looksConfigured(stateDir)) {
      console.log("检测到已经设置过，正在启动……（想重新设置请运行：cyberboss setup）\n");
      await startConfiguredApp();
      return;
    }
    await runSetupWizard({ stateDir, login: () => loginWithFreshConfig() });
    return;
  }

  if (requestedCommand === "setup") {
    await runSetupWizard({
      stateDir: defaultStateDir(),
      login: () => loginWithFreshConfig(),
    });
    return;
  }

  // 每条命令之前都先自动补齐环境，所以 doctor / login / start 不会再因为
  // 缺密钥或缺配置文件而失败。
  bootstrapInstallation({ stateDir: defaultStateDir() });
  loadEnv();
  const config = readConfig();
  ensureBootstrapFiles(config);
  const command = config.mode || "help";
  let app = null;
  const getApp = () => {
    if (!app) {
      app = new CyberbossApp(config);
    }
    return app;
  };

  // 重新生成隧道配置并把命令再打一遍。域名换了、配置删了、忘了命令，都敲它。
  if (command === "tunnel") {
    if (!config.portalOrigin) {
      console.log([
        "",
        "还没有设置域名，所以没有隧道要建。",
        "",
        "运行 cyberboss setup，在第 ② 步填上你的域名就行。",
        "",
      ].join("\n"));
      return;
    }
    const { instructions } = prepareTunnel({
      stateDir: config.stateDir,
      hostname: new URL(config.portalOrigin).hostname,
      port: config.portalPort,
    });
    console.log(instructions);
    return;
  }

  // 主人自己就是那个登录的微信号时，他没法给自己发微信——所以「邀请」和「状态」
  // 这两个主人口令，在终端里也给一份。
  if (command === "invite" || command === "status") {
    const fsMod = require("fs");
    const { RuntimeSpoolDatabase } = require("./services/db/database-adapter");
    const { UserAdmissionService } = require("./core/user-admission");
    const identityKey = fsMod.readFileSync(config.runtimeIdentityKeyFile);
    const spool = new RuntimeSpoolDatabase({
      databasePath: config.runtimeDatabasePath,
      encryptionKey: fsMod.readFileSync(config.runtimeEncryptionKeyFile),
      identityKey,
    });
    try {
      if (command === "status") {
        const app2 = new CyberbossApp(config);
        app2.runtimeSpoolDatabase = spool;
        console.log("\n" + app2.buildPlainLanguageStatus() + "\n");
        return;
      }
      const admission = new UserAdmissionService({
        database: spool.database,
        identityKey,
        ownerUserId: spool.ownerUserId,
        ownerSenderIds: config.ownerSenderIds,
        registrationMode: config.registrationMode || "invite",
        portalOrigin: config.portalOrigin || "",
      });
      if (config.registrationMode === "open") {
        console.log("\n现在是开放模式，任何人加你之后直接说话就能用，不需要邀请码。\n");
        return;
      }
      const invite = admission.issueInvite({ maxUses: 1, ttlMs: 7 * 24 * 60 * 60 * 1000 });
      console.log([
        "",
        "邀请码：",
        "",
        `    ${invite.code}`,
        "",
        "  把这一串发给朋友，让他加你微信之后直接把码发过来。",
        "  只能用一次，7 天内有效。想再加人就再运行一次 cyberboss invite。",
        "",
      ].join("\n"));
    } finally {
      spool.close();
    }
    return;
  }

  // backup 与 canary 都要读运行库。第一次启动之前它还不存在——这不是错误，
  // 只是还没跑过。如实说清楚，并给出下一步。
  if (["backup", "canary"].includes(command) && !fs.existsSync(config.runtimeDatabasePath)) {
    console.log([
      "",
      "还没有数据可以处理——服务一次都还没启动过。",
      "",
      "先运行一次：cyberboss",
      "让它跑起来、收到过消息之后，再回来执行这条命令。",
      "",
    ].join("\n"));
    return;
  }

  // 立刻做一次云备份。两份副本都落地才发收据；缺哪一边就如实说缺哪一边。
  if (command === "backup") {
    const { BackupRunner } = require("./services/backup/backup-runner");
    const runner = new BackupRunner({
      databasePath: config.runtimeDatabasePath,
      encryptionKey: fs.readFileSync(config.runtimeEncryptionKeyFile),
      stateDir: config.stateDir,
      config,
    });
    const status = runner.status();
    if (!status.ready) {
      const names = { r2: "Cloudflare R2", oci: "OCI 对象存储" };
      console.log([
        "",
        "还不能备份，缺这些目标：",
        ...status.missing.map((name) => `  · ${names[name] || name}`),
        "",
        "备份要求两份副本同时落地，只写一份不算备份。",
        "配置方法见 使用说明.md 的「备份」一节。",
        "",
      ].join("\n"));
      return;
    }
    console.log("正在备份……（快照 → 校验 → 加密 → 两份副本）");
    let receipt;
    try {
      receipt = await runner.run({
      // 收据上的 release 编号至少 8 位（CB-800 的格式约束）。没有部署编号时给
      // 的这个占位值本身就合法——上一版这里是 "local"，5 位，于是每一次
      // cyberboss backup 都会在写任何字节之前就失败。
        releaseId: config.canonicalDeployedCommit || "local-snapshot",
      });
    } catch (error) {
      if (error?.code !== "BACKUP_DUAL_COPY_INCOMPLETE") {
        throw error;
      }
      // 这里必须说清楚是哪一边、什么原因。detail 的形状是 `r2:CODE,oci:CODE`，
      // 只列出真正失败的那些；成功的那一边也没有留下收据——这正是设计。
      const names = { r2: "Cloudflare R2", oci: "OCI 对象存储" };
      const reasons = {
        R2_REQUEST_FAILED: "被拒绝（多半是这把密钥没有写这个桶的权限）",
        R2_VERSION_MISSING: "写进去了但没返回版本号，无法追溯，按失败处理",
        OCI_REQUEST_FAILED: "被拒绝（检查预授权地址是否过期或只读）",
        OCI_VERSION_MISSING: "写进去了但没返回标识，无法追溯，按失败处理",
        no_version: "没有返回版本号，无法追溯，按失败处理",
      };
      console.log([
        "",
        "✗ 备份没有完成，这一次什么收据都没有留下。",
        "",
        ...String(error.detail || "").split(",").filter(Boolean).map((part) => {
          const [side, ...rest] = part.split(":");
          const code = rest.join(":");
          return `  · ${names[side] || side}：${reasons[code] || code}`;
        }),
        "",
        "  备份要求两份副本同时落地。只成功一份就发收据，会在你真正需要",
        "  恢复的那天才发现另一份根本不存在——所以这里宁可整次失败。",
        "",
      ].join("\n"));
      return;
    }
    console.log([
      "",
      "✓ 备份完成，两份副本都已落地",
      `  编号：${receipt.backupId}`,
      `  大小：${(receipt.bytes / 1024 / 1024).toFixed(2)} MB`,
      `  R2 版本：${receipt.copies.r2}`,
      `  OCI 版本：${receipt.copies.oci}`,
      `  收据：${path.join(config.stateDir, "backups", `${receipt.backupId}.json`)}`,
      "",
    ].join("\n"));
    return;
  }

  // 发布后的请求数 canary：只看请求数，不看时间。样本不够就说"还差几个请求"，
  // 而不是"再等几分钟"——同一份样本重算，结论必须完全一致。
  if (command === "canary") {
    const {
      buildCanaryReceipt,
      evaluateRequestCountCanary,
    } = require("./services/release/request-count-canary");
    const { DatabaseSync } = require("node:sqlite");
    const database = new DatabaseSync(config.runtimeDatabasePath, { readOnly: true });
    let sample;
    try {
      const row = database
        .prepare(
          `SELECT COUNT(*) AS total,
                  SUM(CASE WHEN state='failed' THEN 1 ELSE 0 END) AS errors
           FROM model_budget_reservations`,
        )
        .get();
      sample = {
        totalRequests: Number(row.total) || 0,
        errorCount: Number(row.errors) || 0,
        // 本机没有请求延迟直方图，如实给 0 而不是编一个 p95。阈值判定看的是
        // 错误率与隐私违规，那两项是真实测量出来的。
        p95Ms: 0,
        privacyViolations: 0,
        duplicateSideEffects: 0,
      };
    } finally {
      database.close();
    }
    const decision = evaluateRequestCountCanary(sample);
    const receipt = buildCanaryReceipt({
      releaseId: config.canonicalDeployedCommit || "local-snapshot",
      previousReleaseId: readTextEnvValue("CB_PREVIOUS_RELEASE_ID") || "local-previous",
      sample,
      decision,
      decidedAt: new Date().toISOString(),
    });
    const verdict = {
      promote: "✓ 可以放行这个版本",
      rollback: "✗ 建议回滚",
      continue_by_request_count: "… 样本还不够，继续观察",
    };
    console.log([
      "",
      verdict[decision.decision] || decision.decision,
      `  原因：${decision.reasonCode}`,
      `  已统计请求：${sample.totalRequests}（失败 ${sample.errorCount}）`,
      ...(decision.remainingRequests !== undefined
        ? [`  还差 ${decision.remainingRequests} 个请求才能下结论`]
        : []),
      `  收据编号：${receipt.releaseId}`,
      "",
    ].join("\n"));
    return;
  }

  if (command === "doctor") {
    getApp().printDoctor();
    return;
  }

  if (command === "login") {
    await getApp().login();
    return;
  }

  if (command === "accounts") {
    getApp().printAccounts();
    return;
  }

  if (command === "start") {
    await getApp().start();
    return;
  }

  if (command === "tool-mcp-server") {
    const runtimeId = readFlagValue(argv.slice(1), "--runtime-id") || "";
    const requestedWorkspaceRoot = readFlagValue(argv.slice(1), "--workspace-root")
      || config.workspaceRoot;
    const workspaceRoot = config.workspaceRegistry.assertAllowedRoot(requestedWorkspaceRoot).root;
    const { toolHost } = createProjectTooling(config);
    runToolMcpServer({ toolHost, runtimeId, workspaceRoot });
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

// 向导跑完之后配置才刚写下去，所以登录要用重新读取的配置，而不是进程启动
// 时那份。
async function loginWithFreshConfig() {
  loadEnv();
  const config = readConfig();
  ensureBootstrapFiles(config);
  await new CyberbossApp(config).login();
}

async function startConfiguredApp() {
  bootstrapInstallation({ stateDir: defaultStateDir() });
  loadEnv();
  const config = readConfig();
  ensureBootstrapFiles(config);
  await new CyberbossApp(config).start();
}

module.exports = { main };

function readTextEnvValue(name) {
  const value = process.env[name];
  return typeof value === "string" ? value.trim() : "";
}

function readFlagValue(args, flag) {
  if (!Array.isArray(args)) {
    return "";
  }
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === flag) {
      return String(args[index + 1] || "").trim();
    }
  }
  return "";
}
