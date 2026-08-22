import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const service = path.join(projectRoot, "service", "harness_service.py");
const games = new Map([
  ["原神", "genshin"],
  ["崩铁", "hsr"],
  ["绝区零", "zzz"],
  ["鸣潮", "wuwa"],
  ["异环", "nte"],
]);

function runSync(source, fallback) {
  const probe = String.raw`
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location("harness_service", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
catalog, report = module.synchronize_catalog(
    pathlib.Path(sys.argv[2]), "http://127.0.0.1:3099", pathlib.Path(sys.argv[3]), deploy=True
)
print(json.dumps({"count": catalog["count"], "report": report}))
`;
  const result = spawnSync("/usr/bin/python3", ["-c", probe, service, source, fallback], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("refresh deploys complete SMB pairs into the durable local master", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-service-sync-"));
  const source = path.join(root, "smb");
  const fallback = path.join(root, "master");
  for (const [gameName] of games) {
    const variant = path.join(source, gameName, "character", "skins", "default");
    fs.mkdirSync(variant, { recursive: true });
    fs.writeFileSync(path.join(variant, "light.png"), `${gameName}-light`);
    fs.writeFileSync(path.join(variant, "dark.png"), `${gameName}-dark`);
    fs.writeFileSync(path.join(variant, "meta.json"), JSON.stringify({ characterZh: gameName, variantZh: "默认" }));
  }

  const first = runSync(source, fallback);
  assert.equal(first.count, 5);
  assert.deepEqual(first.report, {
    status: "ready",
    message: "SMB、本地与总目录均为 5 个；本次部署 5 个",
    smbCount: 5,
    localCount: 5,
    catalogCount: 5,
    deployedCount: 5,
    missingFromSMB: 0,
    missingGames: [],
  });
  for (const [, game] of games) {
    assert.equal(fs.readFileSync(path.join(fallback, game, "character", "default", "light.png"), "utf8").endsWith("-light"), true);
    assert.equal(fs.existsSync(path.join(fallback, game, "character", "default", "meta.json")), true);
  }

  const localOnly = path.join(fallback, "nte", "local-only", "default");
  fs.mkdirSync(localOnly, { recursive: true });
  fs.writeFileSync(path.join(localOnly, "light.png"), "local-light");
  fs.writeFileSync(path.join(localOnly, "dark.png"), "local-dark");
  const second = runSync(source, fallback);
  assert.equal(second.count, 6);
  assert.equal(second.report.status, "partial");
  assert.equal(second.report.smbCount, 5);
  assert.equal(second.report.localCount, 6);
  assert.equal(second.report.missingFromSMB, 1);
  assert.equal(second.report.deployedCount, 0);

  fs.writeFileSync(path.join(source, "原神", "character", "skins", "default", "light.png"), "原神-light-updated");
  const third = runSync(source, fallback);
  assert.equal(third.report.deployedCount, 1);
  assert.equal(fs.readFileSync(path.join(fallback, "genshin", "character", "default", "light.png"), "utf8"), "原神-light-updated");
  fs.rmSync(root, { recursive: true, force: true });
});

test("refresh reports an incomplete SMB partition without deleting the complete local catalog", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-service-partial-"));
  const source = path.join(root, "smb");
  const fallback = path.join(root, "master");
  for (const [gameName, game] of games) {
    const local = path.join(fallback, game, "character", "default");
    fs.mkdirSync(local, { recursive: true });
    fs.writeFileSync(path.join(local, "light.png"), `${gameName}-local-light`);
    fs.writeFileSync(path.join(local, "dark.png"), `${gameName}-local-dark`);
    fs.mkdirSync(path.join(source, gameName), { recursive: true });
    if (game === "nte") continue;
    const remote = path.join(source, gameName, "character", "skins", "default");
    fs.mkdirSync(remote, { recursive: true });
    fs.writeFileSync(path.join(remote, "light.png"), `${gameName}-remote-light`);
    fs.writeFileSync(path.join(remote, "dark.png"), `${gameName}-remote-dark`);
  }

  const result = runSync(source, fallback);
  assert.equal(result.count, 5);
  assert.equal(result.report.status, "partial");
  assert.equal(result.report.smbCount, 4);
  assert.equal(result.report.localCount, 5);
  assert.equal(result.report.catalogCount, 5);
  assert.equal(result.report.missingFromSMB, 1);
  assert.deepEqual(result.report.missingGames, ["nte"]);
  assert.equal(fs.existsSync(path.join(fallback, "nte", "character", "default", "light.png")), true);
  fs.rmSync(root, { recursive: true, force: true });
});
