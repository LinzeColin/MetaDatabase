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
const configRoot = path.join(kitRoot, "config");
const scriptsRoot = path.join(kitRoot, "scripts");
const installer = path.join(scriptsRoot, "install-controlled-workspace.sh");
const builder = path.join(scriptsRoot, "build-controlled-workspace-artifacts.py");
const releaseId = "0123456789abcdef0123456789abcdef01234567";

function read(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

test("CB-120 pins the canonical no-clone client and official GitHub CLI asset", () => {
  const versions = JSON.parse(
    read(path.join(configRoot, "no-clone-client-versions.json"))
  );
  assert.equal(versions.schema_version, 1);
  assert.equal(versions.task_id, "CB-120");
  assert.deepEqual(versions.private_db_client, {
    source_repository: "LinzeColin/KMOS",
    source_path: "KMDatabase/machine/tools/private_db_client.py",
    sha256:
      "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa",
    access_mode: "no_clone_client",
    real_operation_activation: "activation_pending",
  });
  assert.equal(versions.github_cli.version, "2.96.0");
  assert.equal(
    versions.github_cli.archive_sha256,
    "83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60"
  );
  assert.match(
    versions.github_cli.url,
    /^https:\/\/github\.com\/cli\/cli\/releases\/download\/v2\.96\.0\//
  );
});

test("workspace registry is single-alias, sparse, path-bounded and below 8 GiB", () => {
  const registry = JSON.parse(
    read(path.join(configRoot, "workspaces.json.example"))
  );
  const budget = JSON.parse(
    read(path.join(configRoot, "workspace-budget.json"))
  );
  const gitSystemConfig = read(
    path.join(configRoot, "cyberboss.gitconfig")
  );
  const workspace = registry.workspaces.cyberboss;

  assert.equal(registry.default_alias, "cyberboss");
  assert.equal(registry.workspace_base, "/srv/cyberboss-workspaces");
  assert.deepEqual(Object.keys(registry.workspaces), ["cyberboss"]);
  assert.equal(workspace.root, "/srv/cyberboss-workspaces/cyberboss");
  assert.deepEqual(workspace.sparse_paths, ["CyberBoss", ".github"]);
  assert.deepEqual(workspace.root_integration_paths, [".github"]);
  assert.equal(workspace.root_integration_write, false);
  assert.deepEqual(workspace.write_globs, ["CyberBoss/**"]);
  assert.equal(workspace.max_bytes, 4 * 1024 ** 3);
  assert.equal(budget.hard_stop_workspace_bytes, 8 * 1024 ** 3);
  assert.deepEqual(budget.forbidden_cleanup_flags, ["--prune=now"]);
  assert.equal(
    gitSystemConfig,
    "[safe]\n\tdirectory = /srv/cyberboss-workspaces/cyberboss\n"
  );
  assert.doesNotMatch(
    JSON.stringify(budget.cleanup_commands),
    /--prune=now/
  );
});

test("controlled installer check mode is write-free and commit-bound", () => {
  const result = spawnSync(
    "bash",
    [installer, "--check", "--release-id", releaseId],
    { encoding: "utf8" }
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(
    result.stdout,
    new RegExp(
      `CONTROLLED_WORKSPACE_CHECK=PASS release_id=${releaseId} ` +
        "persistent_writes=false live_commands=false private_database_clone=false"
    )
  );

  const shortId = spawnSync(
    "bash",
    [installer, "--check", "--release-id", "deadbeef"],
    { encoding: "utf8" }
  );
  assert.equal(shortId.status, 2);
  assert.match(shortId.stdout, /release_id_must_be_full_lowercase_git_sha/);
});

test("installer keeps candidate, identities, workspace and data boundaries explicit", () => {
  const source = read(installer);

  assert.match(source, /CURRENT_AFTER.*CURRENT_BEFORE/s);
  assert.match(source, /current_changed=false/);
  assert.match(source, /service_must_be_inactive/);
  assert.match(source, /service_must_be_disabled/);
  assert.match(source, /DATA_USER="cyberboss-data"/);
  assert.match(source, /data_identity_code_writable/);
  assert.match(source, /code_identity_data_client_access/);
  assert.match(
    source,
    /config remote\.origin\.partialclonefilter blob:none/
  );
  assert.match(source, /sparse-checkout set CyberBoss \.github/);
  assert.match(source, /WORKSPACE_STAGE=.*\.cb120-/);
  assert.match(
    source,
    /install -d -o "\$CODE_USER" -g "\$CODE_GROUP" -m 0750 "\$WORKSPACE_STAGE"/
  );
  assert.match(source, /git clone --local --no-hardlinks --no-checkout/);
  assert.doesNotMatch(
    source,
    /git -c protocol\.file\.allow=always clone/
  );
  assert.match(source, /GIT_NO_LAZY_FETCH=1 git -C "\$WORKSPACE_STAGE"/);
  assert.match(source, /GIT_CONFIG_SYSTEM="\$GIT_SYSTEM_CONFIG"/);
  assert.match(source, /workspace_object_hardlink/);
  assert.match(
    source,
    /chown -R "\$CODE_USER:\$CODE_GROUP"[\s\\\n]+"\$WORKSPACE_STAGE\/\.git" "\$WORKSPACE_STAGE\/CyberBoss"/
  );
  assert.match(source, /mv -T "\$WORKSPACE_STAGE" "\$WORKSPACE"/);
  assert.match(source, /unsafe_workspace_cleanup_path/);
  assert.match(source, /remote\.origin\.partialclonefilter/);
  assert.match(source, /private_database_clone=false/);
  assert.match(source, /upstream_clarification_received == false/);
  assert.match(source, /npm_config_cache=/);
  assert.match(source, /ci[\s\\\n]+--ignore-scripts --no-audit --no-fund/);
  assert.doesNotMatch(source, /systemctl\s+(?:start|enable)/);
  assert.doesNotMatch(source, /git\s+clone[^\n]*Private-Database/i);
  assert.match(source, /forbidden_cleanup_flags/);
  assert.match(
    source,
    /"--prune=now" not in json\.dumps\(budget\.get\("cleanup_commands"\)\)/
  );
});

test("artifact builder makes a local promisor seed without publishing", () => {
  const source = read(builder);

  assert.match(source, /--filter=blob:none/);
  assert.match(source, /uploadpack\.allowFilter=true/);
  assert.match(source, /GIT_NO_LAZY_FETCH/);
  assert.match(source, /"CyberBoss", "\.github"/);
  assert.match(source, /artifact:\/\/LinzeColin\/MetaDatabase/);
  assert.match(source, /"remote_publication": "none"/);
  assert.match(source, /"clone_private_database": False/);
  assert.match(source, /"upstream_clarification_received": False/);
  assert.doesNotMatch(source, /git",\s*"push"/);
});
