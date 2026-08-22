const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  compareVersions,
  resolveMacInstallTarget,
  rollbackApplicationPath,
  selectRelease,
} = require("../src/runtime/updater.cjs");
const packageJson = require("../package.json");

test("compares stable and prerelease versions", () => {
  assert.equal(compareVersions("1.2.0", "1.1.9"), 1);
  assert.equal(compareVersions("1.2.0", "1.2.0-rc.1"), 1);
  assert.equal(compareVersions("1.2.0-rc.2", "1.2.0-rc.1"), 1);
});

test("desktop version is a canonical Kimi Code version", () => {
  assert.match(packageJson.version, /^\d+\.\d+\.\d+$/);
});

test("selects only a newer matching Kimi desktop asset", () => {
  const releases = [{
    tag_name: "kimi-code-desktop-v0.2.0",
    draft: false,
    prerelease: false,
    assets: [{ name: "Kimi Code Desktop-0.2.0-mac-arm64.zip", size: 10, browser_download_url: "https://github.com/file" }],
  }, {
    tag_name: "other-product-v9.0.0",
    draft: false,
    prerelease: false,
    assets: [],
  }];
  assert.equal(selectRelease(releases, { currentVersion: "0.1.0", platform: "darwin", arch: "arm64" }).version, "0.2.0");
  assert.equal(selectRelease(releases, { currentVersion: "0.2.0", platform: "darwin", arch: "arm64" }), null);
});

test("ignores the retired private community version line", () => {
  const releases = [{
    tag_name: "kimi-code-desktop-community-v0.3.0",
    draft: false,
    prerelease: true,
    assets: [{ name: "Kimi-Code-Desktop-0.3.0-macos-arm64-NOT-NOTARIZED.zip", browser_download_url: "https://github.com/file" }],
  }];
  assert.equal(selectRelease(releases, { currentVersion: "0.2.0", platform: "darwin", arch: "arm64" }), null);
});

test("redirects an updater launched from rollback to the canonical app", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kimi-updater-target-"));
  try {
    const home = path.join(root, "home");
    const updatesRoot = path.join(home, ".kimi-code", "desktop-updates");
    const canonical = path.join(home, "Applications", "Kimi Code.app");
    const rollback = path.join(updatesRoot, "rollback", "0.38.0-old", "Kimi Code.app");
    fs.mkdirSync(canonical, { recursive: true });
    fs.mkdirSync(path.join(rollback, "Contents", "MacOS"), { recursive: true });
    assert.equal(resolveMacInstallTarget({
      executable: path.join(rollback, "Contents", "MacOS", "Kimi Code"),
      updatesRoot,
      home,
    }), canonical);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("stores rollback apps with a non-app suffix", () => {
  const target = "/Users/test/Applications/Kimi Code.app";
  const rollback = rollbackApplicationPath("/Users/test/.kimi-code/desktop-updates", "0.38.0", 42, target);
  assert.equal(rollback, "/Users/test/.kimi-code/desktop-updates/rollback/0.38.0-42/Kimi Code.app.rollback");
  assert.equal(rollback.endsWith(".app"), false);
});
