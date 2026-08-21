const { spawnSync } = require("node:child_process");
const path = require("node:path");

module.exports = async function preserveLocalMacIdentity(context) {
  if (process.platform !== "darwin" || process.env.KIMI_STABLE_ADHOC_IDENTITY !== "1") return;
  const appId = context.packager.appInfo.id;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  const requirement = `=designated => identifier "${appId}"`;
  const result = spawnSync("/usr/bin/codesign", [
    "--force", "--deep", "--sign", "-",
    "--identifier", appId,
    "--requirements", requirement,
    appPath,
  ], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr || `Unable to sign ${appPath}`);
};
