const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const project = path.resolve(__dirname, "..");
const kit = path.join(
  project,
  "docs/product_design/v0.0.0.4/implementation-kit",
);

function read(relative) {
  return fs.readFileSync(path.join(project, relative), "utf8");
}

test("CB-130 keeps one systemd cgroup and a fixed non-shell entrypoint", () => {
  const unit = read(
    "docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-cloud.service",
  );
  const runner = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh",
  );
  const acceptance = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-process-family.sh",
  );
  const supervisor = read("app/scripts/cloud-supervisor.js");
  assert.match(unit, /^KillMode=control-group$/m);
  assert.match(unit, /\/usr\/bin\/flock -n .*bridge\.lock/);
  assert.match(runner, /exec "\$NODE" \.\/scripts\/cloud-supervisor\.js/);
  assert.doesNotMatch(runner, /\/bin\/bash -lc|\beval\b/);
  assert.match(supervisor, /detached: false/);
  assert.match(supervisor, /shell: false/);
  assert.doesNotMatch(supervisor, /\.unref\(\)|detached: true/);
  assert.match(acceptance, /--kill-whom=main --signal=SIGKILL/);
  assert.match(acceptance, /old_cgroup_member_retained/);
  assert.doesNotMatch(acceptance, /--kill-whom=all/);
});

test("runtime, status and simulator binds are fail-closed to exact loopback ports", () => {
  const supervisor = read("app/scripts/cloud-supervisor.js");
  const runner = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh",
  );
  const health = JSON.parse(
    read(
      "docs/product_design/v0.0.0.4/implementation-kit/config/cloud-process-health.json",
    ),
  );
  assert.equal(health.runtime_endpoint, "ws://127.0.0.1:8765");
  assert.equal(health.health_endpoint, "http://127.0.0.1:8780/healthz");
  assert.equal(health.ready_endpoint, "http://127.0.0.1:8780/readyz");
  assert.match(supervisor, /const STATUS_HOST = "127\.0\.0\.1"/);
  assert.match(supervisor, /const STATUS_PORT = 8780/);
  assert.match(runner, /ws:\/\/127\.0\.0\.1:8765/);
  assert.match(runner, /CB_HTTP_HOST.*127\.0\.0\.1/);
});

test("health, readiness and protected status never disclose private runtime fields", () => {
  const health = JSON.parse(
    read(
      "docs/product_design/v0.0.0.4/implementation-kit/config/cloud-process-health.json",
    ),
  );
  assert.deepEqual(health.critical_components, ["runtime", "channel", "bridge"]);
  assert.equal(health.recovery.mode, "probe_driven");
  assert.equal(health.recovery.fixed_wait, false);
  assert.equal(health.recovery.llm_call, false);
  assert.deepEqual(health.privacy, {
    allow_process_ids: false,
    allow_account_or_user_ids: false,
    allow_thread_ids: false,
    allow_tokens: false,
    allow_prompt_or_result: false,
    allow_absolute_paths: false,
  });
});

test("install check is read-only and all CB-130 shell gates avoid fixed delay commands", () => {
  const installer = path.join(kit, "scripts/install-cloud-process-family.sh");
  const installerSource = fs.readFileSync(installer, "utf8");
  const result = spawnSync(
    "bash",
    [installer, "--check", "--release-id", "0".repeat(40)],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /persistent_writes=false/);
  assert.match(result.stdout, /live_commands=false/);
  assert.match(
    installerSource,
    /\$2 == "tests" && \$3 ~ \/\^\[0-9\]\+\$\/ \{ count = \$3 \}/,
  );
  assert.doesNotMatch(installerSource, /grep -E '\^# tests/);
  for (const name of [
    "run-cyberboss.sh",
    "health-check.sh",
    "install-cloud-process-family.sh",
    "accept-cloud-process-family.sh",
  ]) {
    const source = fs.readFileSync(path.join(kit, "scripts", name), "utf8");
    assert.doesNotMatch(source, /^\s*sleep(?:\s|$)/m, name);
  }
});

test("artifact and deployment contracts preserve strict compliance and no publication", () => {
  const builder = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
  );
  const installer = read(
    "docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
  );
  const contract = read("docs/governance/RUN_CONTRACT_P1_4_CB_130.md");
  for (const source of [builder, installer, contract]) {
    assert.match(source, /AGPL-3\.0-only AND GPL-3\.0-only/);
    assert.match(source, /upstream_clarification_received/);
  }
  assert.match(builder, /"remote_publication": "none"/);
  assert.match(installer, /switch_current == false/);
  assert.match(contract, /不创建新 repo/);
  assert.match(contract, /不 push[，、]不创建 PR\/tag\/release/);
});
