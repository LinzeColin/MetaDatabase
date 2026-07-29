import { spawnSync } from "node:child_process";

const MINIMUM = Object.freeze([3, 11]);

export function resolvePythonCommand(env = process.env) {
  const candidates = [env.WRP_PYTHON, "python3.13", "python3.12", "python3.11", "python3"].filter(Boolean);
  for (const candidate of [...new Set(candidates)]) {
    const result = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    const version = `${result.stdout || ""}${result.stderr || ""}`.match(/Python\s+(\d+)\.(\d+)/u);
    if (result.status === 0 && version && isSupported(Number(version[1]), Number(version[2]))) return candidate;
  }
  throw new Error("验证拒绝：需要 Python 3.11+。可通过 WRP_PYTHON 指定已安装解释器。");
}

function isSupported(major, minor) {
  return major > MINIMUM[0] || (major === MINIMUM[0] && minor >= MINIMUM[1]);
}
