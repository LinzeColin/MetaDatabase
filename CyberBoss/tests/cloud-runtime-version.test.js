const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const projectRoot = path.resolve(__dirname, "..");
const kitRoot = path.join(
  projectRoot,
  "docs/product_design/v0.0.0.4/implementation-kit"
);
const runtimeSpecPath = path.join(kitRoot, "config/runtime-versions.json");
const envExamplePath = path.join(kitRoot, "config/cyberboss.env.example");
const installScript = path.join(kitRoot, "scripts/install-runtime-toolchain.sh");
const probeScript = path.join(kitRoot, "scripts/probe-codex-app-server.mjs");
const runScript = path.join(kitRoot, "scripts/run-cyberboss.sh");
const releaseId = "0123456789abcdef0123456789abcdef01234567";

function read(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

test("runtime spec pins exact official Node and Codex archives", () => {
  const spec = JSON.parse(read(runtimeSpecPath));

  assert.equal(spec.schema_version, 1);
  assert.equal(spec.task_id, "CB-110");
  assert.equal(spec.platform, "linux-x64");
  assert.deepEqual(spec.node, {
    version: "24.18.0",
    version_output: "v24.18.0",
    license: "MIT",
    archive_url: "https://nodejs.org/dist/v24.18.0/node-v24.18.0-linux-x64.tar.xz",
    archive_sha256: "55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742",
  });
  assert.equal(spec.codex.version, "0.146.0-alpha.3.1");
  assert.equal(
    spec.codex.main_archive_sha256,
    "3473d6d6416979b43118d203fa4e584c4e5af939206eee854d9db60c7555df17"
  );
  assert.equal(
    spec.codex.platform_archive_sha256,
    "d495bfa843ed9198327cc087b69b99aff09a66d4f5e7139137bc72d02ccf3e53"
  );
  assert.match(
    spec.codex.main_archive_url,
    /^https:\/\/registry\.npmjs\.org\/@openai\/codex\/-\/codex-[^/]+\.tgz$/
  );
  assert.match(
    spec.codex.platform_archive_url,
    /^https:\/\/registry\.npmjs\.org\/@openai\/codex\/-\/codex-[^/]+-linux-x64\.tgz$/
  );
  assert.doesNotMatch(JSON.stringify(spec), /\blatest\b|git\+|github\.com/i);
});

test("runtime installer check mode is write-free and commit-bound", () => {
  const result = spawnSync(
    "bash",
    [installScript, "--check", "--release-id", releaseId],
    { encoding: "utf8" }
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(
    result.stdout,
    new RegExp(
      `RUNTIME_TOOLCHAIN_CHECK=PASS release_id=${releaseId} ` +
      "node=24\\.18\\.0 codex=0\\.146\\.0-alpha\\.3\\.1 " +
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

test("runtime installer verifies archives before extraction and avoids global package install", () => {
  const install = read(installScript);

  assert.match(install, /download_and_verify "\$NODE_URL" "\$NODE_SHA256"/);
  assert.match(install, /download_and_verify "\$CODEX_MAIN_URL" "\$CODEX_MAIN_SHA256"/);
  assert.match(install, /download_and_verify[\s\\\n]+"?\$CODEX_PLATFORM_URL"?/);
  assert.match(install, /actual="\$\(sha256sum "\$destination"/);
  assert.match(install, /tar -xJf "\$NODE_ARCHIVE"/);
  assert.match(install, /tar -xzf "\$CODEX_MAIN_ARCHIVE"/);
  assert.match(install, /assert_no_escaping_symlink/);
  assert.match(install, /node:sqlite/);
  assert.match(install, /app-server --help/);
  assert.match(install, /\/opt\/cyberboss-cloud\/shared\/toolchains/);
  assert.match(install, /version-manifest\.json/);
  assert.match(install, /auth_content_read=false/);
  assert.match(install, /claude_binary=absent/);
  assert.doesNotMatch(install, /\bnpm\s+(?:install|add)\b/);
  assert.doesNotMatch(install, /\bapt-get\b|\/usr\/local\/bin\/(?:node|codex)/);
  assert.doesNotMatch(install, /\bcurl\b[^\n]*(?:github\.com|raw\.githubusercontent)/i);
});

test("Codex probe is fixed to loopback and performs readiness plus protocol initialize only", () => {
  const probe = read(probeScript);

  assert.match(probe, /ws:\/\/127\.0\.0\.1:8765/);
  assert.match(probe, /\/readyz/);
  assert.match(probe, /method: "initialize"/);
  assert.match(probe, /method: "initialized"/);
  assert.match(probe, /experimentalApi: true/);
  assert.match(probe, /authenticated_turn_started: false/);
  assert.match(probe, /credential_content_read: false/);
  assert.match(probe, /public_callback_used: false/);
  assert.doesNotMatch(probe, /0\.0\.0\.0|turn\/start|thread\/start/);
});

test("Claude dispatch stays disabled unless both feature and eval gates are true", () => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-cb110-gate-"));
  const appRoot = path.join(fixtureRoot, "app");
  const stateDir = path.join(fixtureRoot, "state");
  fs.mkdirSync(path.join(appRoot, "current"), { recursive: true });
  fs.mkdirSync(stateDir, { recursive: true });

  const baseEnv = {
    PATH: process.env.PATH,
    HOME: fixtureRoot,
    CB_APP_ROOT: appRoot,
    CYBERBOSS_STATE_DIR: stateDir,
    CYBERBOSS_CODEX_ENDPOINT: "ws://127.0.0.1:8765",
    CB_RUNTIME_DB: path.join(stateDir, "runtime.db"),
    CB_START_COMMAND: "true",
    CYBERBOSS_RUNTIME: "claudecode",
  };

  try {
    for (const [feature, evaluation, expected] of [
      ["false", "false", 2],
      ["true", "false", 2],
      ["false", "true", 2],
      ["true", "true", 0],
    ]) {
      const result = spawnSync("bash", [runScript], {
        encoding: "utf8",
        env: {
          ...baseEnv,
          CB_CLAUDE_RUNTIME: feature,
          CB_CLAUDE_EVAL_PASSED: evaluation,
        },
      });
      assert.equal(
        result.status,
        expected,
        `feature=${feature} eval=${evaluation}\n${result.stdout}${result.stderr}`
      );
      if (expected === 2) {
        assert.match(result.stderr, /Claude adapter disabled/);
        assert.doesNotMatch(result.stdout, /Starting CyberBoss Cloud/);
      } else {
        assert.match(result.stdout, /Starting CyberBoss Cloud/);
      }
    }
  } finally {
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  }
});

test("deployed defaults retain Codex and explicitly disable both Claude gates", () => {
  const envExample = read(envExamplePath);
  const run = read(runScript);

  assert.match(envExample, /^CYBERBOSS_RUNTIME=codex$/m);
  assert.match(envExample, /^CB_CLAUDE_RUNTIME=false$/m);
  assert.match(envExample, /^CB_CLAUDE_EVAL_PASSED=false$/m);
  assert.match(run, /\$\{CB_CLAUDE_RUNTIME:-false\}" != "true"/);
  assert.match(run, /\$\{CB_CLAUDE_EVAL_PASSED:-false\}" != "true"/);
});
