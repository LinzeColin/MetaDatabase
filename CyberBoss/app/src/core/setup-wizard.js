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
    "② 设置页面（可跳过）",
    "   用户要填自己的 AI 密钥时，会打开一个网页。",
    "   如果你有自己的网址（必须是 https 开头），填在这里；",
    "   没有就直接按回车跳过——软件照样能跑，只是暂时打不开那个网页。",
    "",
  ].join("\n"),
  portalInvalid: "   ⚠ 网址要以 https:// 开头，而且后面不带斜杠和路径。再填一次，或直接回车跳过。",
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
    "   不用填。启动之后，第一个给它发消息的人就是主人（也就是你）。",
    "   之后再来的人都是普通用户，要邀请码才能开通。",
    "",
  ].join("\n"),
  done: (stateDir) => [
    "",
    LINE,
    "  设置完成 ✓",
    LINE,
    "",
    "  现在做这两件事：",
    "",
    "    1. 用你自己的微信，给刚才登录的那个号发一句「你好」",
    "       → 你就成为主人了",
    "",
    "    2. 想让朋友也能用，就发「邀请」",
    "       → 会回给你一串邀请码，转发给他即可",
    "",
    "  其它随时可用的中文口令：帮助 / 设置 / 状态 / 邀请",
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
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const answer = await io.ask("   网址（回车跳过）> ");
      if (!answer) break;
      if (isBareHttpsOrigin(answer)) {
        updates.CB_PORTAL_ORIGIN = answer;
        write("   ✓ 已记住\n");
        break;
      }
      write(COPY.portalInvalid);
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
    return Object.freeze({
      stateDir: result.stateDir,
      envFile,
      settings: Object.freeze({ ...updates }),
      loggedIn: shouldLogin,
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
  createPrompt,
  isBareHttpsOrigin,
  looksConfigured,
  runSetupWizard,
};
