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
