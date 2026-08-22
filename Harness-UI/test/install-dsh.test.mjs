import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("installs the DSH adapter into a desktop profile without starting DSH", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-dsh-"));
  const profileRoot = path.join(root, "profiles", "desktop");
  fs.mkdirSync(path.join(profileRoot, "node_modules"), { recursive: true });
  fs.writeFileSync(path.join(profileRoot, "package.json"), JSON.stringify({
    name: "fixture",
    dependencies: {},
    dsh: { profile: { bundles: [] } },
  }));

  const result = spawnSync(process.execPath, [path.join(projectRoot, "scripts", "install-dsh.mjs"), "--apply", "--dsh-root", root], {
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const profile = JSON.parse(fs.readFileSync(path.join(profileRoot, "package.json"), "utf8"));
  assert.equal(profile.dependencies["dsh-harness-ui-skins"], `link:${path.join(root, "plugins", "dsh-harness-ui-skins")}`);
  assert.ok(profile.dsh.profile.bundles.includes("dsh-harness-ui-skins"));
  assert.ok(fs.existsSync(path.join(profileRoot, "node_modules", "dsh-harness-ui-skins", "lib", "client.js")));
  fs.rmSync(root, { recursive: true, force: true });
});

test("replaces an existing linked profile module without following it", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-dsh-link-"));
  const profileRoot = path.join(root, "profiles", "desktop");
  const pluginRoot = path.join(root, "plugins", "dsh-harness-ui-skins");
  const moduleRoot = path.join(profileRoot, "node_modules", "dsh-harness-ui-skins");
  fs.mkdirSync(pluginRoot, { recursive: true });
  fs.mkdirSync(path.dirname(moduleRoot), { recursive: true });
  fs.symlinkSync(pluginRoot, moduleRoot, "dir");
  fs.writeFileSync(path.join(profileRoot, "package.json"), JSON.stringify({
    name: "fixture",
    dependencies: { "dsh-harness-ui-skins": `link:${pluginRoot}` },
    dsh: { profile: { bundles: ["dsh-harness-ui-skins"] } },
  }));

  const result = spawnSync(process.execPath, [path.join(projectRoot, "scripts", "install-dsh.mjs"), "--apply", "--dsh-root", root], {
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.ok(fs.lstatSync(moduleRoot).isDirectory());
  assert.ok(fs.existsSync(path.join(moduleRoot, "lib", "client.js")));
  const client = fs.readFileSync(path.join(moduleRoot, "lib", "client.js"), "utf8");
  assert.match(client, /\/api\/next/);
  assert.match(client, /event\.metaKey \|\| event\.ctrlKey/);
  assert.match(client, /event\.shiftKey/);
  fs.rmSync(root, { recursive: true, force: true });
});

test("stores macOS app rollbacks with a non-app suffix", () => {
  const dshInstaller = fs.readFileSync(path.join(projectRoot, "dsh-desktop", "install-dsh-update.py"), "utf8");
  const harnessInstaller = fs.readFileSync(path.join(projectRoot, "scripts", "install-release-macos.sh"), "utf8");
  assert.match(dshInstaller, /f"\{TARGET\.name\}\.rollback"/);
  assert.match(harnessInstaller, /Harness UI\.app\.rollback/);
});
