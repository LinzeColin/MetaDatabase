const fs = require("node:fs");
const https = require("node:https");
const path = require("node:path");
const { spawn } = require("node:child_process");

const API_URL = "https://api.github.com/repos/LinzeColin/MetaDatabase/releases?per_page=50";
const TAG_PATTERNS = {
  stable: /^kimi-code-desktop-v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/,
  community: /^kimi-code-desktop-community-v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/,
};
const DOWNLOAD_HOSTS = new Set(["github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"]);

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

function communityAssetSuffix(platform, arch) {
  if (platform === "darwin") return `-macos-${arch}-NOT-NOTARIZED.zip`;
  if (platform === "win32") return `-windows-${arch}-UNSIGNED-setup.exe`;
  return null;
}

function selectRelease(releases, { currentVersion, platform = process.platform, arch = process.arch, channel = "stable" }) {
  const pattern = TAG_PATTERNS[channel];
  const suffix = channel === "community" ? communityAssetSuffix(platform, arch) : assetSuffix(platform, arch);
  if (!pattern) throw new Error(`未知更新通道：${channel}`);
  if (!suffix) return null;
  return (Array.isArray(releases) ? releases : [])
    .filter((release) => !release.draft && (channel === "community" ? release.prerelease : !release.prerelease))
    .map((release) => {
      const match = String(release.tag_name || "").match(pattern);
      if (!match) return null;
      const asset = (release.assets || []).find((candidate) => String(candidate.name || "").endsWith(suffix));
      return asset ? { channel, release, version: match[1], asset } : null;
    })
    .filter(Boolean)
    .filter((candidate) => compareVersions(candidate.version, currentVersion) > 0)
    .sort((left, right) => compareVersions(right.version, left.version))[0] || null;
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

class DesktopUpdater {
  constructor({ currentVersion, updatesRoot, installerSource, bundleId, platform = process.platform, arch = process.arch }) {
    this.currentVersion = currentVersion;
    this.updatesRoot = updatesRoot;
    this.installerSource = installerSource;
    this.bundleId = bundleId;
    this.platform = platform;
    this.arch = arch;
  }

  async check() {
    const releases = await fetchReleases();
    const stable = selectRelease(releases, {
      currentVersion: this.currentVersion,
      platform: this.platform,
      arch: this.arch,
    });
    const community = selectRelease(releases, {
      currentVersion: this.currentVersion,
      platform: this.platform,
      arch: this.arch,
      channel: "community",
    });
    const update = stable || community;
    return update ? { status: "available", ...update } : { status: "current", currentVersion: this.currentVersion };
  }

  async download(update) {
    fs.mkdirSync(this.updatesRoot, { recursive: true, mode: 0o700 });
    const name = path.basename(update.asset.name);
    const destination = path.join(this.updatesRoot, name);
    return downloadAsset(update.asset.browser_download_url, destination, { expectedSize: Number(update.asset.size) || 0 });
  }

  prepareMacInstall({ archive, version, executable = process.execPath, pid = process.pid }) {
    if (this.platform !== "darwin") throw new Error("当前平台不使用 macOS 更新安装器");
    const target = macApplicationPath(executable);
    if (!target) throw new Error("无法识别当前 Kimi Code.app 的位置");
    fs.accessSync(path.dirname(target), fs.constants.W_OK);
    const helper = path.join(this.updatesRoot, "install-macos.sh");
    fs.copyFileSync(this.installerSource, helper);
    fs.chmodSync(helper, 0o700);
    const rollback = path.join(this.updatesRoot, "rollback", `${version}-${Date.now()}`, path.basename(target));
    fs.mkdirSync(path.dirname(rollback), { recursive: true, mode: 0o700 });
    const child = spawn("/bin/sh", [helper, String(pid), archive, target, rollback, this.bundleId, version], {
      detached: true,
      stdio: "ignore",
    });
    child.unref();
  }
}

module.exports = {
  DesktopUpdater,
  assetSuffix,
  communityAssetSuffix,
  compareVersions,
  downloadAsset,
  fetchReleases,
  macApplicationPath,
  selectRelease,
};
