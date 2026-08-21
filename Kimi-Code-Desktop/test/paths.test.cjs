const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { desktopUserDataPath, executableName, kimiHome, resolveKimiCli } = require("../src/runtime/paths.cjs");

test("uses platform-specific executable names", () => {
  assert.equal(executableName("darwin"), "kimi");
  assert.equal(executableName("win32"), "kimi.exe");
});

test("prefers an explicit KIMI_CLI_PATH", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "kimi-paths-"));
  const executable = path.join(directory, "custom-kimi");
  fs.writeFileSync(executable, "fixture");
  const result = resolveKimiCli({
    env: { KIMI_CLI_PATH: executable, PATH: "" },
    platform: "darwin",
    homeDir: directory,
    developmentRoot: directory,
    resourcesPath: directory,
  });
  assert.equal(result.path, executable);
  fs.rmSync(directory, { recursive: true, force: true });
});

test("uses KIMI_CODE_HOME without copying user data", () => {
  assert.equal(kimiHome({ KIMI_CODE_HOME: "/tmp/kimi-home" }, "/unused"), "/tmp/kimi-home");
  assert.equal(kimiHome({}, "/Users/example"), path.join("/Users/example", ".kimi-code"));
});

test("keeps the legacy Electron profile when an existing desktop install used kimi-shell", () => {
  const appData = fs.mkdtempSync(path.join(os.tmpdir(), "kimi-app-data-"));
  const legacy = path.join(appData, "kimi-shell");
  fs.mkdirSync(legacy);
  assert.equal(desktopUserDataPath(appData), legacy);
  fs.rmSync(appData, { recursive: true, force: true });
});

test("uses the canonical profile name on a fresh install", () => {
  const appData = fs.mkdtempSync(path.join(os.tmpdir(), "kimi-app-data-"));
  assert.equal(desktopUserDataPath(appData), path.join(appData, "Kimi Code"));
  fs.rmSync(appData, { recursive: true, force: true });
});
