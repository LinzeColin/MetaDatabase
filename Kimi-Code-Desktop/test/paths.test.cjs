const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  desktopUserDataPath,
  executableName,
  kimiHome,
  prepareStableMacCli,
  resolveKimiCli,
} = require("../src/runtime/paths.cjs");

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

test("moves the packaged CLI to the stable permission path without touching user data", {
  skip: process.platform !== "darwin",
}, () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kimi-stable-cli-"));
  const resources = path.join(root, "resources");
  const home = path.join(root, "home");
  const bundled = path.join(resources, "kimi", "kimi");
  const installed = path.join(home, "bin", "kimi");
  fs.mkdirSync(path.dirname(bundled), { recursive: true });
  fs.mkdirSync(path.dirname(installed), { recursive: true });
  fs.writeFileSync(bundled, "#!/bin/sh\nprintf '0.38.0\\n'\n", { mode: 0o755 });
  fs.writeFileSync(installed, "#!/bin/sh\nprintf '0.37.2\\n'\n", { mode: 0o755 });
  fs.writeFileSync(path.join(home, "config.json"), "keep-me");

  const result = prepareStableMacCli({
    expectedVersion: "0.38.0",
    kimiHomeDir: home,
    resourcesPath: resources,
    now: () => 1234,
  });

  assert.equal(result, installed);
  assert.equal(fs.readFileSync(installed, "utf8"), fs.readFileSync(bundled, "utf8"));
  assert.equal(fs.readFileSync(path.join(home, "config.json"), "utf8"), "keep-me");
  assert.equal(
    fs.readFileSync(path.join(home, "desktop-updates", "cli-rollback", "0.37.2-1234", "kimi"), "utf8"),
    "#!/bin/sh\nprintf '0.37.2\\n'\n",
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test("keeps an already matching stable CLI in place", {
  skip: process.platform !== "darwin",
}, () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kimi-stable-cli-"));
  const resources = path.join(root, "resources");
  const home = path.join(root, "home");
  const bundled = path.join(resources, "kimi", "kimi");
  const installed = path.join(home, "bin", "kimi");
  fs.mkdirSync(path.dirname(bundled), { recursive: true });
  fs.mkdirSync(path.dirname(installed), { recursive: true });
  fs.writeFileSync(bundled, "#!/bin/sh\nprintf '0.38.0\\n'\n", { mode: 0o755 });
  fs.writeFileSync(installed, "#!/bin/sh\nprintf '0.38.0\\n'\n# existing\n", { mode: 0o755 });

  prepareStableMacCli({ expectedVersion: "0.38.0", kimiHomeDir: home, resourcesPath: resources });

  assert.match(fs.readFileSync(installed, "utf8"), /existing/);
  assert.equal(fs.existsSync(path.join(home, "desktop-updates", "cli-rollback")), false);
  fs.rmSync(root, { recursive: true, force: true });
});
