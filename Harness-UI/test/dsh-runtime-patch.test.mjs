import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const patcher = path.join(projectRoot, "dsh-desktop", "patch-dsh-runtime.py");
const service = path.join(projectRoot, "service", "harness_service.py");

function patchRuntime(source) {
  const probe = String.raw`
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("dsh_runtime_patch", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
patched, changes = module.patch_runtime(sys.stdin.read())
print(json.dumps({"source": patched, "changes": changes}))
`;
  const result = spawnSync("/usr/bin/python3", ["-c", probe, patcher], { input: source, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

const legacyRuntime = `class Runtime {
\tasync downloadAndOpenUpdate(version, signal) {
\t\tif (this.platform === "darwin") {
\t\t\tconst openError = await shell.openPath(artifactPath);
\t\t\tif (openError !== "") throw new Error(\`dsh-plugin-desktop: failed to open update disk image: \${openError}\`);
\t\t\tsignal.throwIfAborted();
\t\t\tawait dialog.showMessageBox({ buttons: ["OK"] });
\t\t\treturn;
\t\t}
\t\tif ((await dialog.showMessageBox({ buttons: ["Later"] })).response !== 0) return;
\t}
\trebuildTrayMenu() {
\t\tconst status = this.contributedTrayItems("status");
\t\tconst template = [{ label: "open" }];
\t}
\tasync mount(spec) {
\t\tconst icon = nativeImage.createFromPath(spec.iconPath);
\t\tif (icon.isEmpty()) throw new Error(\`dsh-plugin-desktop: failed to load application icon \${spec.iconPath}\`);
\t}
}`;

const modernRuntime = `function macApplicationMenuTemplate(appName, locale, additions = []) {
\tconst label = LABELS[locale];
\tconst nativeAdditions = additions.length === 0 ? [{ type: "separator" }] : [
\t\t{ type: "separator" },
\t\t...additions,
\t\t{ type: "separator" }
\t];
\treturn [
\t\t{
\t\t\tlabel: appName,
\t\t\tsubmenu: [...nativeAdditions]
\t\t},
\t\t{
\t\t\tlabel: label.file,
\t\t\tsubmenu: []
\t\t},
\t\t{
\t\t\tlabel: label.view,
\t\t\tsubmenu: []
\t\t}
\t];
}
class Runtime {
\tasync downloadAndOpenUpdate(version, signal) {
\t\tif (platform === "darwin") {
\t\t\tconst openError = await shell.openPath(artifactPath);
\t\t\tif (openError !== "") throw new Error(\`dsh-plugin-desktop: failed to open update disk image: \${openError}\`);
\t\t\tsignal.throwIfAborted();
\t\t\tawait dialog.showMessageBox({ buttons: ["OK"] });
\t\t\treturn;
\t\t}
\t\tif ((await dialog.showMessageBox({ buttons: ["Later"] })).response !== 0) return;
\t}
\tasync mount(spec) {
\t\tconst icon = nativeImage.createFromPath(spec.iconPath);
\t\tif (icon.isEmpty()) throw new Error(\`dsh-plugin-desktop: failed to load application icon \${spec.iconPath}\`);
\t}
\tbuildApplicationMenuItems() {
\t\tconst tools = this.contributedTrayItems("tools");
\t\tconst profiles = this.contributedTrayItems("profiles");
\t\tconst items = [];
\t\tif (tools.length > 0) items.push(...tools);
\t\tif (tools.length > 0 && profiles.length > 0) items.push({ type: "separator" });
\t\tif (profiles.length > 0) items.push(...profiles);
\t\treturn items;
\t}
\tcontributedTrayItems(group) {
\t\treturn [...this.trayItems.values()].filter((item) => item.group === group).sort((left, right) => left.order - right.order).map((item) => {
\t\t\tconst common = {
\t\t\t\tlabel: item.label(),
\t\t\t\tenabled: item.enabled?.() ?? true
\t\t\t};
\t\t\tif (item.submenu !== void 0) return {
\t\t\t\t...common,
\t\t\t\tsubmenu: item.submenu().map((command) => ({
\t\t\t\t\tlabel: command.label(),
\t\t\t\t\tenabled: command.enabled?.() ?? true,
\t\t\t\t\t...command.type === void 0 ? {} : { type: command.type },
\t\t\t\t\t...command.checked === void 0 ? {} : { checked: command.checked() },
\t\t\t\t\tclick: this.trayCommand(() => command.invoke())
\t\t\t\t}))
\t\t\t};
\t\t\treturn {
\t\t\t\t...common,
\t\t\t\tclick: this.trayCommand(() => item.invoke())
\t\t\t};
\t\t});
\t}
\t/** Contain asynchronous contribution failures outside Electron menu callbacks. */
\ttrayCommand(invoke) { return invoke; }
}`;

for (const [name, source] of [["legacy runtime", legacyRuntime], ["upstream 2.0.2 runtime", modernRuntime]]) {
  test(`patches and re-patches the ${name} without changing app data`, () => {
    const first = patchRuntime(source);
    assert.ok(first.source.includes("260822-external-icon-v2"));
    assert.ok(first.source.includes("icon.png"));
    assert.ok(first.source.includes("260822-safe-macos-update"));
    assert.ok(first.source.includes("260822-normal-app-menu"));
    if (name === "upstream 2.0.2 runtime") {
      assert.ok(first.source.includes("260822-harness-native-menu"));
      assert.ok(first.source.includes('contributedTrayItems("harness")'));
      assert.ok(first.source.includes("harnessTopLevel"));
      assert.ok(first.source.includes("260822-harness-native-command-tree"));
    }
    const second = patchRuntime(first.source);
    assert.deepEqual(second.changes, []);
    assert.equal(second.source, first.source);
  });
}

test("serves the durable local master before a TCC-restricted SMB asset", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-service-assets-"));
  const source = path.join(root, "smb");
  const fallback = path.join(root, "master");
  const local = path.join(fallback, "genshin", "amber", "default", "light.png");
  const smb = path.join(source, "原神", "amber", "skins", "default", "light.png");
  fs.mkdirSync(path.dirname(local), { recursive: true });
  fs.mkdirSync(path.dirname(smb), { recursive: true });
  fs.writeFileSync(local, "local");
  fs.writeFileSync(smb, "smb");
  const probe = String.raw`
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location("harness_service", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
store = module.HarnessStore(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4]), "http://127.0.0.1:3099")
print(json.dumps([str(path) for path in store.assets("/assets/%E5%8E%9F%E7%A5%9E/amber/default/light")]))
`;
  const result = spawnSync("/usr/bin/python3", ["-c", probe, service, path.join(root, "data"), source, fallback], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), [local, smb]);
  fs.rmSync(root, { recursive: true, force: true });
});

test("keeps a complete catalog available while SMB is temporarily unreachable", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-service-fallback-"));
  const fallback = path.join(root, "master");
  for (const game of ["genshin", "hsr", "zzz", "wuwa", "nte"]) {
    const variant = path.join(fallback, game, "character", "default");
    fs.mkdirSync(variant, { recursive: true });
    fs.writeFileSync(path.join(variant, "light.png"), "light");
    fs.writeFileSync(path.join(variant, "dark.png"), "dark");
  }
  const probe = String.raw`
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location("harness_service", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
catalog = module.build_catalog(pathlib.Path(sys.argv[2]), "http://127.0.0.1:3099", pathlib.Path(sys.argv[3]))
print(json.dumps({"source": catalog["source"], "count": catalog["count"]}))
`;
  const missingSmb = path.join(root, "unmounted-smb");
  const result = spawnSync("/usr/bin/python3", ["-c", probe, service, missingSmb, fallback], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), { source: "local-fallback", count: 5 });
  fs.rmSync(root, { recursive: true, force: true });
});

test("advances shared state atomically without enabling rotation", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-service-next-"));
  const probe = String.raw`
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location("harness_service", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data = pathlib.Path(sys.argv[2])
data.mkdir(parents=True, exist_ok=True)
catalog = {"version": 1, "source": "local", "generated": "now", "count": 3, "entries": [{"id": value} for value in ["one", "two", "three"]]}
state = {"mode": "gallery", "selected": "one", "cycle": ["one", "two", "three"], "cursor": 0}
module.atomic_json(data / "catalog.json", catalog)
module.atomic_json(data / "state.json", state)
store = module.HarnessStore(data, data / "smb", data / "fallback", "http://127.0.0.1:3099")
print(json.dumps(store.next_state(42)))
`;
  const result = spawnSync("/usr/bin/python3", ["-c", probe, service, root], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const state = JSON.parse(result.stdout);
  assert.equal(state.mode, "gallery");
  assert.equal(state.selected, "two");
  assert.equal(state.cursor, 2);
  assert.equal(state.lastRotate, 42);
  fs.rmSync(root, { recursive: true, force: true });
});
