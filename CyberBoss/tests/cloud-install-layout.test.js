const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const projectRoot = path.resolve(__dirname, "..");
const kitRoot = path.join(
  projectRoot,
  "docs/product_design/v0.0.0.4/implementation-kit"
);
const installScript = path.join(kitRoot, "scripts/install-layout.sh");
const verifyScript = path.join(kitRoot, "scripts/verify-installation.sh");
const unitPath = path.join(kitRoot, "systemd/cyberboss-cloud.service");
const journalPath = path.join(kitRoot, "config/cyberboss-journald.conf");
const releaseId = "0123456789abcdef0123456789abcdef01234567";

function read(relativePath) {
  return fs.readFileSync(path.join(kitRoot, relativePath), "utf8");
}

test("install layout has a read-only check mode bound to a full commit SHA", () => {
  const result = spawnSync(
    "bash",
    [installScript, "--check", "--release-id", releaseId],
    { encoding: "utf8" }
  );

  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(
    result.stdout,
    new RegExp(
      `INSTALL_CHECK=PASS release_id=${releaseId} ` +
        "live_commands=false persistent_writes=false"
    )
  );

  const shortId = spawnSync(
    "bash",
    [installScript, "--check", "--release-id", "deadbeef"],
    { encoding: "utf8" }
  );
  assert.equal(shortId.status, 2);
  assert.match(shortId.stdout, /release_id_must_be_full_lowercase_git_sha/);
});

test("cloud unit is non-root, cgroup-killed, sandboxed and log-bounded", () => {
  const unit = fs.readFileSync(unitPath, "utf8");
  for (const directive of [
    "User=cyberboss",
    "Group=cyberboss",
    "WorkingDirectory=/opt/cyberboss-cloud/current",
    "EnvironmentFile=/etc/cyberboss/cyberboss.env",
    "ExecStart=/usr/bin/flock -n /var/lib/cyberboss/locks/bridge.lock /opt/cyberboss-cloud/current/implementation-kit/scripts/run-cyberboss.sh",
    "Restart=on-failure",
    "KillMode=control-group",
    "MemoryHigh=768M",
    "MemoryMax=1152M",
    "TasksMax=256",
    "LogNamespace=cyberboss",
    "ProtectSystem=strict",
    "ReadOnlyPaths=/opt/cyberboss-cloud /etc/cyberboss",
    "ReadWritePaths=/var/lib/cyberboss /srv/cyberboss-workspaces",
  ]) {
    assert.match(unit, new RegExp(`^${directive.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`, "m"));
  }
  assert.doesNotMatch(unit, /^User=root$/m);
  assert.doesNotMatch(unit, /^ReadWritePaths=.*\/etc/m);
  assert.doesNotMatch(unit, /^ReadWritePaths=.*\/opt/m);
});

test("P1.1 installs only the disabled cloud unit and an immutable release", () => {
  const install = fs.readFileSync(installScript, "utf8");

  assert.match(install, /systemd\/cyberboss-cloud\.service/);
  assert.match(install, /find "\$STAGING" -type d -exec chmod 0555/);
  assert.match(install, /find "\$STAGING" -type f .* -exec chmod 0444/);
  assert.match(install, /mv -Tf "\$CURRENT_TMP" "\$APP_ROOT\/current"/);
  assert.match(install, /if \[\[ ! -e "\$CURRENT_BACKUP" \]\]; then/);
  assert.match(install, /existing_current_backup_mode_mismatch/);
  assert.match(install, /if \[\[ "\$RELEASE_EXISTS" == false \]\]; then/);
  assert.match(install, /resource_dropin_sha256/);
  assert.match(install, /unit_must_remain_inactive/);
  assert.match(install, /unit_must_remain_disabled/);
  assert.doesNotMatch(install, /systemd\/\*\.\{service,timer\}/);
  assert.doesNotMatch(install, /systemctl enable/);
  assert.doesNotMatch(install, /systemctl start/);
});

test("journal namespace and app cap are independently bounded", () => {
  const journal = fs.readFileSync(journalPath, "utf8");
  const install = fs.readFileSync(installScript, "utf8");

  assert.match(journal, /^SystemMaxUse=@CB_MAX_LOG_BYTES@$/m);
  assert.match(journal, /^RuntimeMaxUse=67108864$/m);
  assert.match(journal, /^MaxRetentionSec=14day$/m);
  assert.match(journal, /^RateLimitIntervalSec=30s$/m);
  assert.match(journal, /^RateLimitBurst=500$/m);
  assert.match(install, /CB_MAX_LOG_BYTES/);
  assert.match(install, /journald@cyberboss\.conf\.d/);
});

test("verification is accelerated, count-based and has no fixed sleep", () => {
  const verify = fs.readFileSync(verifyScript, "utf8");

  assert.match(verify, /for _iteration in \$\(seq 1 100\)/);
  assert.match(verify, /systemctl kill --kill-who=all --signal=KILL/);
  assert.match(verify, /restart_passes=\$\(\(restart_passes \+ 1\)\)/);
  assert.match(verify, /contention_denied=\$\(\(contention_denied \+ 1\)\)/);
  assert.match(verify, /ready_predicate=active_pid_and_lock/);
  assert.match(verify, /CB_SYSTEMD_MEMORY_HIGH/);
  assert.match(verify, /root_required_for_identity_checks/);
  assert.match(verify, /fixed_sleep=0 llm_calls=0/);
  assert.doesNotMatch(verify, /\bsleep\s+[0-9]/);
  assert.doesNotMatch(verify, /\b(codex|claude|openai)\b/i);
});
