"use strict";

// 中文安装向导。目标只有一个：一个没碰过命令行的人，运行 `cyberboss` 之后
// 照着屏幕上的话做，就能把软件跑起来。
//
// 它不问任何"技术问题"。密钥、工作区、配置文件都在 bootstrap 里自动生成；
// 这里只问三件用户真的知道答案的事，而且每一件都有默认值可以直接回车跳过。

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const { bootstrapInstallation, readEnvFile, updateEnvFile } = require("./bootstrap");
const {
  buildTunnelInstructions,
  defaultCredentialsFile,
  originForHostname,
  writeTunnelConfig,
} = require("./cloudflare-tunnel");

const DEFAULT_PORTAL_PORT = 8787;
const TUNNEL_NAME = "cyberboss";

// 把 cloudflared 的配置写好并返回该给用户看的那段说明。凭据文件的路径按
// cloudflared 自己的约定给出：`tunnel create` 执行完它就会出现在那儿。
function prepareTunnel({ stateDir, hostname, port = DEFAULT_PORTAL_PORT, homeDir = require("node:os").homedir() }) {
  const configPath = writeTunnelConfig({
    stateDir,
    tunnelName: TUNNEL_NAME,
    hostname,
    credentialsFile: defaultCredentialsFile(homeDir, TUNNEL_NAME),
    localPort: port,
  });
  return {
    configPath,
    hostname,
    instructions: buildTunnelInstructions({
      tunnelName: TUNNEL_NAME,
      hostname,
      configPath,
    }),
  };
}

const LINE = "─".repeat(46);

// 每条提示都说清楚"这是什么"和"不填会怎样"，不出现术语。
const COPY = Object.freeze({
  banner: [
    "",
    LINE,
    "  CyberBoss 安装向导",
    "  接下来大约 2 分钟，跟着提示按回车就行。",
    LINE,
    "",
  ].join("\n"),
  bootstrapDone: (result) => [
    "① 正在准备运行环境……",
    `   数据目录：${result.stateDir}`,
    result.encryptionKey.created || result.identityKey.created
      ? "   已生成两把只有你能读的密钥（首次安装才会生成，之后永远不动它）"
      : "   密钥已存在，保持不变",
    result.workspace.created
      ? "   已创建工作目录与配置文件"
      : "   工作目录与配置文件已存在",
    "   ✓ 完成",
    "",
  ].join("\n"),
  askPortal: [
    "② 设置页面的域名（可跳过）",
    "   用户要填自己的 AI 密钥时，会打开一个网页。这个网页需要一个域名。",
    "",
    "   有域名就填域名本身，不用带 https，比如：  boss.example.com",
    "   （我会顺便把 Cloudflare 隧道的配置也替你写好）",
    "",
    "   没有就直接回车跳过——软件照样能跑，只是那个网页暂时打不开。",
    "",
  ].join("\n"),
  portalInvalid: "   ⚠ 只填域名本身就行，像 boss.example.com。再填一次，或直接回车跳过。",
  askRegistration: [
    "③ 谁可以使用（可跳过）",
    "   1) 邀请制——只有拿到你给的邀请码的人才能用（推荐）",
    "   2) 开放——任何加你微信的人都能直接用",
    "   直接回车＝选 1。",
    "",
  ].join("\n"),
  askLogin: [
    "④ 微信登录",
    "   接下来会显示一个二维码，用你要当机器人的那个微信扫它。",
    "   已经登录过就直接按回车跳过。",
    "",
  ].join("\n"),
  ownerHint: [
    "⑤ 谁是主人",
    "   不用填。你扫码登录的那个微信号本身就是主人。",
    "   别人给它发消息都是普通用户，要邀请码才能开通。",
    "",
  ].join("\n"),
  done: (stateDir) => [
    "",
    LINE,
    "  设置完成 ✓",
    LINE,
    "",
    "  你扫码的那个微信号就是主人，不用再做认领。",
    "",
    "  想让朋友也能用：",
    "",
    "    cyberboss invite",
    "",
    "  会给你一串邀请码，转发给朋友，他加你之后把码发过来就能开通。",
    "",
    "  朋友在微信里能用的中文口令：帮助 / 设置 / 记一下 / 提醒我 / 最近7天",
    "  你自己在终端里：cyberboss invite（发邀请）· cyberboss status（看状况）",
    "",
    `  配置都存在这里：${path.join(stateDir, ".env")}`,
    "  以后再启动，只要运行：cyberboss start",
    "",
  ].join("\n"),
});

function createPrompt(input = process.stdin, output = process.stdout) {
  const rl = readline.createInterface({ input, output });
  return {
    ask(question) {
      return new Promise((resolve) => rl.question(question, (answer) => resolve(String(answer || "").trim())));
    },
    close() {
      rl.close();
    },
  };
}

function isBareHttpsOrigin(value) {
  return /^https:\/\/[^/?#\s]+$/.test(value);
}

// 判断是不是"已经装过了"。装过就不再走完整向导，直接启动。
function looksConfigured(stateDir) {
  const env = readEnvFile(path.join(stateDir, ".env"));
  const accountsDir = path.join(stateDir, "accounts");
  const hasAccount = fs.existsSync(accountsDir)
    && fs.readdirSync(accountsDir).some((name) => name.endsWith(".json"));
  return hasAccount || env.has("CB_SETUP_COMPLETED_AT");
}

async function runSetupWizard({
  stateDir,
  output = process.stdout,
  prompt = null,
  login = null,
  port = DEFAULT_PORTAL_PORT,
  now = () => new Date(),
} = {}) {
  const write = (text) => output.write(`${text}\n`);
  const result = bootstrapInstallation({ stateDir });
  const io = prompt || createPrompt();
  const envFile = result.envFile;
  const updates = {};

  try {
    write(COPY.banner);
    write(COPY.bootstrapDone(result));

    write(COPY.askPortal);
    let tunnel = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const answer = await io.ask("   域名（回车跳过）> ");
      if (!answer) break;
      // 用户很可能连 https:// 一起粘进来，这不是错误，去掉就是。
      const hostname = answer.replace(/^https?:\/\//i, "").replace(/\/.*$/, "").trim();
      let origin;
      try {
        origin = originForHostname(hostname);
      } catch {
        write(COPY.portalInvalid);
        continue;
      }
      updates.CB_PORTAL_ORIGIN = origin;
      write(`   ✓ 已记住 ${origin}\n`);
      tunnel = prepareTunnel({ stateDir: result.stateDir, hostname, port });
      break;
    }

    write(COPY.askRegistration);
    const mode = await io.ask("   选 1 或 2（回车＝1）> ");
    updates.CB_REGISTRATION_MODE = mode === "2" ? "open" : "invite";
    write(`   ✓ ${updates.CB_REGISTRATION_MODE === "open" ? "任何人都能直接用" : "需要邀请码"}\n`);

    write(COPY.askLogin);
    const wantsLogin = await io.ask("   现在扫码登录？(回车＝是，输 n 跳过) > ");
    const shouldLogin = wantsLogin.toLowerCase() !== "n";

    write(COPY.ownerHint);
    updates.CB_SETUP_COMPLETED_AT = now().toISOString();
    updateEnvFile(envFile, updates);

    if (shouldLogin && typeof login === "function") {
      write("   正在打开微信登录……\n");
      try {
        await login();
      } catch (error) {
        write(`   ⚠ 登录没成功：${friendlyLoginError(error)}`);
        write("     不影响已完成的设置。稍后单独运行：cyberboss login\n");
      }
    }

    write(COPY.done(result.stateDir));
    if (tunnel) {
      write(tunnel.instructions);
    }
    return Object.freeze({
      stateDir: result.stateDir,
      envFile,
      settings: Object.freeze({ ...updates }),
      loggedIn: shouldLogin,
      tunnel: tunnel ? Object.freeze({ configPath: tunnel.configPath, hostname: tunnel.hostname }) : null,
    });
  } finally {
    if (!prompt) {
      io.close();
    }
  }
}

function friendlyLoginError(error) {
  const code = String(error?.code || error?.message || "");
  if (/ENOTFOUND|ECONNREFUSED|ETIMEDOUT|network/i.test(code)) {
    return "连不上网络，检查一下网络再试";
  }
  return "请稍后重试";
}

module.exports = {
  COPY,
  DEFAULT_PORTAL_PORT,
  TUNNEL_NAME,
  createPrompt,
  isBareHttpsOrigin,
  looksConfigured,
  prepareTunnel,
  runSetupWizard,
};
