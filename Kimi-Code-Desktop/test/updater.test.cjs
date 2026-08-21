const assert = require("node:assert/strict");
const test = require("node:test");
const { compareVersions, selectRelease } = require("../src/runtime/updater.cjs");
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
