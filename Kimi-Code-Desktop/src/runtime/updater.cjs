const fs = require("node:fs");
const https = require("node:https");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const API_URL = "https://api.github.com/repos/LinzeColin/MetaDatabase/releases?per_page=50";
const TAG_PATTERN = /^kimi-code-desktop-v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/;
const DOWNLOAD_HOSTS = new Set(["github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"]);
const REVISION_PATTERN = /^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$/;

function versionParts(raw) {
  const match = String(raw || "").match(/^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3]), match[4] || ""] : null;
}

function compareVersions(left, right) {
  const a = versionParts(left);
  const b = versionParts(right);
  if (!a || !b) throw new Error(`无法比较版本：${left} / ${right}`);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] > b[index] ? 1 : -1;
  }
  if (a[3] === b[3]) return 0;
  if (!a[3]) return 1;
  if (!b[3]) return -1;
  return a[3].localeCompare(b[3], "en", { numeric: true });
}

function assetSuffix(platform, arch) {
  if (platform === "darwin") return `-mac-${arch}.zip`;
  if (platform === "win32") return `-win-${arch}.exe`;
  return null;
}

function distributionManifestName(version) {
  return `Kimi.Code.Desktop-${version}-release.json`;
}

function releaseCandidate(release, { platform, arch }) {
  const suffix = assetSuffix(platform, arch);
  if (!suffix || release?.draft || release?.prerelease) return null;
  const match = String(release?.tag_name || "").match(TAG_PATTERN);
  if (!match) return null;
  const asset = (release.assets || []).find((candidate) => String(candidate.name || "").endsWith(suffix));
  return asset ? { channel: "stable", release, version: match[1], asset } : null;
}

function selectRelease(releases, { currentVersion, platform = process.platform, arch = process.arch }) {
  return (Array.isArray(releases) ? releases : [])
    .map((release) => releaseCandidate(release, { platform, arch }))
    .filter(Boolean)
    .filter((candidate) => compareVersions(candidate.version, currentVersion) > 0)
    .sort((left, right) => compareVersions(right.version, left.version))[0] || null;
}

function selectRepairRelease(releases, { currentVersion, platform = process.platform, arch = process.arch }) {
  const candidate = (Array.isArray(releases) ? releases : [])
    .map((release) => releaseCandidate(release, { platform, arch }))
    .find((entry) => entry && compareVersions(entry.version, currentVersion) === 0);
  if (!candidate) return null;
  const manifestAsset = (candidate.release.assets || [])
    .find((asset) => String(asset.name || "") === distributionManifestName(currentVersion));
  return manifestAsset ? { ...candidate, repair: true, manifestAsset } : null;
}

function parseDistributionManifest(raw, expectedVersion) {
  const value = JSON.parse(Buffer.isBuffer(raw) ? raw.toString("utf8") : String(raw || ""));
  if (value?.schema !== 1 || value?.version !== expectedVersion || !REVISION_PATTERN.test(String(value?.revision || ""))) {
    throw new Error("同版本维护更新清单无效");
  }
  return { version: value.version, revision: value.revision };
}

function getBuffer(rawUrl, { maxBytes = 8 * 1024 * 1024, redirects = 5 } = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:") return reject(new Error("更新服务必须使用 HTTPS"));
    const request = https.get(url, {
      timeout: 15000,
      headers: { Accept: "application/vnd.github+json", "User-Agent": "Kimi-Code-Desktop-Updater" },
    }, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location && redirects > 0) {
        response.resume();
        resolve(getBuffer(new URL(response.headers.location, url).href, { maxBytes, redirects: redirects - 1 }));
        return;
      }
      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`更新服务返回 HTTP ${response.statusCode}`));
        return;
      }
      const chunks = [];
      let size = 0;
      response.on("data", (chunk) => {
        size += chunk.length;
        if (size > maxBytes) request.destroy(new Error("更新响应超过允许大小"));
        else chunks.push(chunk);
      });
      response.on("end", () => resolve(Buffer.concat(chunks)));
    });
    request.once("timeout", () => request.destroy(new Error("连接更新服务超时")));
    request.once("error", reject);
  });
}

async function fetchReleases() {
  return JSON.parse((await getBuffer(API_URL)).toString("utf8"));
}

function downloadAsset(rawUrl, destination, { expectedSize = 0, redirects = 5 } = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:" || !DOWNLOAD_HOSTS.has(url.hostname)) {
      reject(new Error("更新下载地址不在受信任的 GitHub 域名中"));
      return;
    }
    const request = https.get(url, {
      timeout: 30000,
      headers: { Accept: "application/octet-stream", "User-Agent": "Kimi-Code-Desktop-Updater" },
    }, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location && redirects > 0) {
        response.resume();
        downloadAsset(new URL(response.headers.location, url).href, destination, { expectedSize, redirects: redirects - 1 }).then(resolve, reject);
        return;
      }
      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`更新下载返回 HTTP ${response.statusCode}`));
        return;
      }
      const temporary = `${destination}.part`;
      const output = fs.createWriteStream(temporary, { mode: 0o600 });
      let received = 0;
      response.on("data", (chunk) => { received += chunk.length; });
      response.pipe(output);
      output.once("error", reject);
      output.once("finish", () => {
        output.close(() => {
          if (expectedSize > 0 && received !== expectedSize) {
            reject(new Error(`更新文件大小不完整：${received} / ${expectedSize}`));
            return;
          }
          fs.renameSync(temporary, destination);
          resolve(destination);
        });
      });
    });
    request.once("timeout", () => request.destroy(new Error("下载更新超时")));
    request.once("error", reject);
  });
}

function macApplicationPath(executable = process.execPath) {
  const candidate = path.resolve(path.dirname(executable), "../..");
  return candidate.endsWith(".app") ? candidate : null;
}

function pathIsInside(root, candidate) {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  return relative === "" || (!path.isAbsolute(relative) && relative !== ".." && !relative.startsWith(`..${path.sep}`));
}

function installLocationFile(updatesRoot) {
  return path.join(updatesRoot, "install-location.json");
}

function storedMacApplicationPath(updatesRoot) {
  try {
    const value = JSON.parse(fs.readFileSync(installLocationFile(updatesRoot), "utf8")).path;
    return typeof value === "string" && path.isAbsolute(value) && value.endsWith(".app") ? path.resolve(value) : null;
  } catch {
    return null;
  }
}

function resolveMacInstallTarget({ executable = process.execPath, updatesRoot, home = os.homedir() }) {
  const current = macApplicationPath(executable);
  if (!current) return null;
  const rollbackRoot = path.join(updatesRoot, "rollback");
  if (!pathIsInside(rollbackRoot, current)) return current;

  const candidates = [
    storedMacApplicationPath(updatesRoot),
    path.join(home, "Applications", "Kimi Code.app"),
    "/Applications/Kimi Code.app",
  ];
  const canonical = candidates.find((candidate) => candidate
    && candidate !== current
    && !pathIsInside(rollbackRoot, candidate)
    && fs.existsSync(candidate));
  if (!canonical) throw new Error("当前从回滚副本运行，未找到正式 Kimi Code.app；请从正式安装位置启动后再更新");
  return canonical;
}

function rollbackApplicationPath(updatesRoot, version, timestamp, target) {
  return path.join(
    updatesRoot,
    "rollback",
    `${version}-${timestamp}`,
    `${path.basename(target)}.rollback`,
  );
}

class DesktopUpdater {
  constructor({ currentVersion, currentRevision = "legacy", updatesRoot, installerSource, bundleId, platform = process.platform, arch = process.arch }) {
    this.currentVersion = currentVersion;
    this.currentRevision = currentRevision;
    this.updatesRoot = updatesRoot;
    this.installerSource = installerSource;
    this.bundleId = bundleId;
    this.platform = platform;
    this.arch = arch;
  }

  async check() {
    const releases = await fetchReleases();
    const update = selectRelease(releases, {
      currentVersion: this.currentVersion,
      platform: this.platform,
      arch: this.arch,
    });
    if (update) return { status: "available", ...update };
    const repair = selectRepairRelease(releases, {
      currentVersion: this.currentVersion,
      platform: this.platform,
      arch: this.arch,
    });
    if (!repair) return { status: "current", currentVersion: this.currentVersion };
    const manifest = parseDistributionManifest(
      await getBuffer(repair.manifestAsset.browser_download_url, { maxBytes: 64 * 1024 }),
      this.currentVersion,
    );
    return manifest.revision === this.currentRevision
      ? { status: "current", currentVersion: this.currentVersion, currentRevision: this.currentRevision }
      : { status: "available", ...repair, revision: manifest.revision };
  }

  async download(update) {
    fs.mkdirSync(this.updatesRoot, { recursive: true, mode: 0o700 });
    const name = path.basename(update.asset.name);
    const destination = path.join(this.updatesRoot, name);
    return downloadAsset(update.asset.browser_download_url, destination, { expectedSize: Number(update.asset.size) || 0 });
  }

  rememberMacInstallLocation(executable = process.execPath) {
    if (this.platform !== "darwin") return;
    const current = macApplicationPath(executable);
    if (!current || pathIsInside(path.join(this.updatesRoot, "rollback"), current)) return;
    fs.mkdirSync(this.updatesRoot, { recursive: true, mode: 0o700 });
    const destination = installLocationFile(this.updatesRoot);
    const temporary = `${destination}.tmp`;
    fs.writeFileSync(temporary, `${JSON.stringify({ version: 1, path: current }, null, 2)}\n`, { mode: 0o600 });
    fs.renameSync(temporary, destination);
  }

  quarantineLegacyMacRollbacks(executable = process.execPath) {
    if (this.platform !== "darwin") return [];
    const rollbackRoot = path.join(this.updatesRoot, "rollback");
    if (!fs.existsSync(rollbackRoot)) return [];
    const current = macApplicationPath(executable);
    const moved = [];
    for (const versionEntry of fs.readdirSync(rollbackRoot, { withFileTypes: true })) {
      if (!versionEntry.isDirectory()) continue;
      const versionDirectory = path.join(rollbackRoot, versionEntry.name);
      for (const appEntry of fs.readdirSync(versionDirectory, { withFileTypes: true })) {
        if (!appEntry.isDirectory() || !appEntry.name.endsWith(".app")) continue;
        const source = path.join(versionDirectory, appEntry.name);
        if (current && path.resolve(source) === path.resolve(current)) continue;
        const destination = `${source}.rollback`;
        if (fs.existsSync(destination)) continue;
        fs.renameSync(source, destination);
        moved.push(destination);
      }
    }
    return moved;
  }

  prepareMacInstall({ archive, version, revision = "", executable = process.execPath, pid = process.pid }) {
    if (this.platform !== "darwin") throw new Error("当前平台不使用 macOS 更新安装器");
    const target = resolveMacInstallTarget({ executable, updatesRoot: this.updatesRoot });
    if (!target) throw new Error("无法识别当前 Kimi Code.app 的位置");
    fs.accessSync(path.dirname(target), fs.constants.W_OK);
    const helper = path.join(this.updatesRoot, "install-macos.sh");
    fs.copyFileSync(this.installerSource, helper);
    fs.chmodSync(helper, 0o700);
    const rollback = rollbackApplicationPath(this.updatesRoot, version, Date.now(), target);
    fs.mkdirSync(path.dirname(rollback), { recursive: true, mode: 0o700 });
    const child = spawn("/bin/sh", [helper, String(pid), archive, target, rollback, this.bundleId, version, revision], {
      detached: true,
      stdio: "ignore",
    });
    child.unref();
  }
}

module.exports = {
  DesktopUpdater,
  assetSuffix,
  compareVersions,
  distributionManifestName,
  downloadAsset,
  fetchReleases,
  macApplicationPath,
  resolveMacInstallTarget,
  rollbackApplicationPath,
  parseDistributionManifest,
  selectRelease,
  selectRepairRelease,
};
