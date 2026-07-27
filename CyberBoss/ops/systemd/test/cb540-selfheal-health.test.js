"use strict";

const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const SCRIPT = path.resolve(__dirname, "..", "cb540-selfheal-health.sh");
const DROP_IN = path.resolve(__dirname, "..", "cb540-selfheal-degraded-channel.conf");

function writeExecutable(target, contents) {
  fs.writeFileSync(target, contents, { encoding: "utf8", mode: 0o700 });
}

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb540-selfheal-"));
  const systemctl = path.join(root, "systemctl");
  const curl = path.join(root, "curl");
  writeExecutable(systemctl, `#!/usr/bin/env bash
if [[ "\${CB540_TEST_SERVICE_ACTIVE:-true}" == "true" ]]; then exit 0; fi
exit 3
`);
  writeExecutable(curl, `#!/usr/bin/env bash
url="\${!#}"
case "$url" in
  */healthz) printf '{"status":"healthy"}\\n\\n200' ;;
  */timeline/) printf '200' ;;
  */readyz)
    case "\${CB540_TEST_READY:-pending}" in
      ready) printf '{"status":"ready","unready_components":[]}\\n\\n200' ;;
      pending) printf '{"status":"unready","unready_components":["channel","bridge"]}\\n\\n503' ;;
      *) printf '{"status":"unready","unready_components":["runtime"]}\\n\\n503' ;;
    esac
    ;;
  *) exit 9 ;;
esac
`);
  t.after(() => fs.rmSync(root, { force: true, recursive: true }));
  return { curl, systemctl };
}

function run(fixture, overrides = {}) {
  return childProcess.spawnSync("bash", [SCRIPT], {
    encoding: "utf8",
    env: {
      ...process.env,
      CB540_CURL_BIN: fixture.curl,
      CB540_SYSTEMCTL_BIN: fixture.systemctl,
      ...overrides,
    },
  });
}

test("CB-540 treats the exact real-channel pending shape as a no-restart degraded state", (t) => {
  const result = run(fixture(t));
  assert.equal(result.status, 1);
  assert.equal(result.stdout, "CB540_SELFHEAL_HEALTH=DEGRADED reason=channel_pending\n");
  assert.equal(result.stderr, "");
});

test("CB-540 returns success only for the exact ready loopback contract", (t) => {
  const result = run(fixture(t), { CB540_TEST_READY: "ready" });
  assert.equal(result.status, 0);
  assert.equal(result.stdout, "CB540_SELFHEAL_HEALTH=PASS readiness=ready\n");
  assert.equal(result.stderr, "");
});

test("CB-540 fails closed for any other readiness shape or inactive cloud service", (t) => {
  const files = fixture(t);
  const unexpected = run(files, { CB540_TEST_READY: "unexpected" });
  assert.equal(unexpected.status, 2);
  assert.equal(unexpected.stdout, "CB540_SELFHEAL_HEALTH=FAILED reason=ready_contract\n");

  const inactive = run(files, { CB540_TEST_SERVICE_ACTIVE: "false" });
  assert.equal(inactive.status, 2);
  assert.equal(inactive.stdout, "CB540_SELFHEAL_HEALTH=FAILED reason=cloud_inactive\n");
});

test("CB-540 systemd override pins the wrapper after any EnvironmentFile value", () => {
  assert.equal(
    fs.readFileSync(DROP_IN, "utf8"),
    "[Service]\n" +
      "ExecStart=\n" +
      "ExecStart=/usr/bin/env CB_HEALTH_SCRIPT=/opt/cyberboss-cloud/current/ops/systemd/cb540-selfheal-health.sh /opt/cyberboss-cloud/current/implementation-kit/scripts/self-heal.sh\n" +
      "SuccessExitStatus=1\n",
  );
});
