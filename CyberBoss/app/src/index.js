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
