const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

module.exports = async function preserveLocalMacIdentity(context) {
  if (process.platform !== "darwin" || process.env.KIMI_STABLE_ADHOC_IDENTITY !== "1") return;
  const appId = context.packager.appInfo.id;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  const officialCli = path.join(context.packager.projectDir, "vendor", "kimi", "current", "kimi");
  const packagedCli = path.join(appPath, "Contents", "Resources", "kimi", "kimi");
  fs.copyFileSync(officialCli, packagedCli);
  fs.chmodSync(packagedCli, 0o755);
  const requirement = `=designated => identifier "${appId}"`;
  const result = spawnSync("/usr/bin/codesign", [
    "--force", "--sign", "-",
    "--identifier", appId,
    "--requirements", requirement,
    appPath,
  ], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr || `Unable to sign ${appPath}`);
};
