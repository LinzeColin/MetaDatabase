import assert from "node:assert/strict";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const updater = path.join(projectRoot, "dsh-desktop", "install-dsh-update.py");

test("makes a staged DSH bundle writable before local patching", () => {
  const probe = String.raw`
import importlib.util, json, pathlib, stat, sys, tempfile
spec = importlib.util.spec_from_file_location("dsh_update", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix="dsh-update-permissions-") as temporary:
    root = pathlib.Path(temporary)
    bundle = root / "DSH Desktop.app"
    runtime = bundle / "Contents" / "Resources" / "runtime.js"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("runtime")
    for directory in [bundle, bundle / "Contents", runtime.parent]:
        directory.chmod(0o555)
    runtime.chmod(0o444)
    module.make_bundle_writable(bundle)
    print(json.dumps({
        "bundleWritable": bool(bundle.stat().st_mode & stat.S_IWUSR),
        "runtimeParentWritable": bool(runtime.parent.stat().st_mode & stat.S_IWUSR),
        "runtimeWritable": bool(runtime.stat().st_mode & stat.S_IWUSR),
    }))
`;
  const result = spawnSync("/usr/bin/python3", ["-c", probe, updater], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    bundleWritable: true,
    runtimeParentWritable: true,
    runtimeWritable: true,
  });
});
