const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

function executableName(platform = process.platform) {
  return platform === "win32" ? "kimi.exe" : "kimi";
}

function isFile(candidate, fsImpl = fs) {
  if (!candidate) return false;
  try {
    return fsImpl.statSync(candidate).isFile();
  } catch {
    return false;
  }
}

function pathCandidates(pathValue, platform, env) {
  const separator = platform === "win32" ? ";" : ":";
  const extensions = platform === "win32"
    ? (env.PATHEXT || ".EXE;.CMD;.BAT").split(";").filter(Boolean)
    : [""];
  const baseName = platform === "win32" ? "kimi" : "kimi";
  const result = [];
  for (const directory of String(pathValue || "").split(separator).filter(Boolean)) {
    for (const extension of extensions) result.push(path.join(directory, baseName + extension.toLowerCase()));
  }
  return result;
}

function candidateList({
  env = process.env,
  platform = process.platform,
  homeDir = os.homedir(),
  resourcesPath = process.resourcesPath,
  developmentRoot,
} = {}) {
  const name = executableName(platform);
  return [
    env.KIMI_CLI_PATH,
    resourcesPath && path.join(resourcesPath, "kimi", name),
    developmentRoot && path.join(developmentRoot, "vendor", "kimi", "current", name),
    path.join(homeDir, ".kimi-code", "bin", name),
    ...pathCandidates(env.PATH, platform, env),
  ].filter(Boolean);
}

function resolveKimiCli(options = {}) {
  const fsImpl = options.fsImpl || fs;
  const candidates = candidateList(options);
  const found = candidates.find((candidate) => isFile(candidate, fsImpl));
  return { path: found || null, candidates };
}

function kimiHome(env = process.env, homeDir = os.homedir()) {
  return env.KIMI_CODE_HOME || path.join(homeDir, ".kimi-code");
}

function cliVersion(candidate, execFileSyncImpl = execFileSync) {
  if (!candidate) return null;
  try {
    return String(execFileSyncImpl(candidate, ["--version"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 5000,
    })).trim().replace(/^v/, "") || null;
  } catch {
    return null;
  }
}

function prepareStableMacCli({
  expectedVersion,
  kimiHomeDir,
  resourcesPath,
  fsImpl = fs,
  execFileSyncImpl = execFileSync,
  now = Date.now,
} = {}) {
  const bundled = resourcesPath && path.join(resourcesPath, "kimi", "kimi");
  if (!expectedVersion || !kimiHomeDir || !isFile(bundled, fsImpl)) return null;
  const bundledVersion = cliVersion(bundled, execFileSyncImpl);
  if (bundledVersion !== expectedVersion) {
    throw new Error(`应用内 Kimi CLI 版本 ${bundledVersion || "未知"} 与桌面版本 ${expectedVersion} 不一致`);
  }

  const binDir = path.join(kimiHomeDir, "bin");
  const stable = path.join(binDir, "kimi");
  const installedVersion = isFile(stable, fsImpl) ? cliVersion(stable, execFileSyncImpl) : null;
  if (installedVersion === expectedVersion) return stable;

  fsImpl.mkdirSync(binDir, { recursive: true });
  if (isFile(stable, fsImpl)) {
    const rollbackDir = path.join(
      kimiHomeDir,
      "desktop-updates",
      "cli-rollback",
      `${installedVersion || "unknown"}-${now()}`,
    );
    fsImpl.mkdirSync(rollbackDir, { recursive: true });
    fsImpl.copyFileSync(stable, path.join(rollbackDir, "kimi"));
  }

  const staged = path.join(binDir, `.kimi-desktop-update-${process.pid}`);
  fsImpl.copyFileSync(bundled, staged);
  fsImpl.chmodSync(staged, 0o755);
  fsImpl.renameSync(staged, stable);
  return stable;
}

function desktopUserDataPath(appDataDir, fsImpl = fs) {
  const legacy = path.join(appDataDir, "kimi-shell");
  return fsImpl.existsSync(legacy) ? legacy : path.join(appDataDir, "Kimi Code");
}

module.exports = {
  candidateList,
  cliVersion,
  desktopUserDataPath,
  executableName,
  kimiHome,
  prepareStableMacCli,
  resolveKimiCli,
};
