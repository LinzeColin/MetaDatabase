const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

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

function desktopUserDataPath(appDataDir, fsImpl = fs) {
  const legacy = path.join(appDataDir, "kimi-shell");
  return fsImpl.existsSync(legacy) ? legacy : path.join(appDataDir, "Kimi Code");
}

module.exports = { candidateList, desktopUserDataPath, executableName, kimiHome, resolveKimiCli };
