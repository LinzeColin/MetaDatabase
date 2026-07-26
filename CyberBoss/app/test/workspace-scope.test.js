const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { CyberbossApp } = require("../src/core/app");
const { readConfig } = require("../src/core/config");
const {
  WorkspaceRegistry,
  WorkspaceRegistryError,
} = require("../src/core/workspace-registry");

function createFixture(t, { withEscape = false } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cyberboss-workspace-scope-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const base = path.join(root, "workspaces");
  const workspaceRoot = path.join(base, "cyberboss");
  const outside = path.join(root, "outside");
  fs.mkdirSync(workspaceRoot, { recursive: true });
  fs.mkdirSync(outside);
  fs.writeFileSync(path.join(workspaceRoot, "sentinel.txt"), "unchanged\n");
  const workspaces = {
    cyberboss: {
      repo: "LinzeColin/MetaDatabase",
      root: workspaceRoot,
      project_subpath: "CyberBoss",
      max_bytes: 4_294_967_296,
      sparse_paths: ["CyberBoss", ".github"],
      root_integration_paths: [".github"],
      root_integration_write: false,
      write_globs: ["CyberBoss/**"],
    },
  };
  if (withEscape) {
    fs.rmSync(workspaceRoot, { recursive: true });
    fs.symlinkSync(outside, workspaceRoot);
  }
  const configPath = path.join(root, "workspaces.json");
  fs.writeFileSync(configPath, `${JSON.stringify({
    schema_version: 1,
    default_alias: "cyberboss",
    workspace_base: base,
    workspaces,
  }, null, 2)}\n`);
  return {
    root,
    base,
    workspaceRoot,
    outside,
    configPath,
    registry: new WorkspaceRegistry({ configPath, workspaceBase: base }),
  };
}

function treeSnapshot(root) {
  const result = [];
  const visit = (current) => {
    for (const name of fs.readdirSync(current).sort()) {
      const candidate = path.join(current, name);
      const stats = fs.lstatSync(candidate);
      const relative = path.relative(root, candidate);
      result.push(`${relative}|${stats.mode}|${stats.size}|${stats.isSymbolicLink() ? fs.readlinkSync(candidate) : ""}`);
      if (stats.isDirectory()) {
        visit(candidate);
      }
    }
  };
  visit(root);
  return result;
}

function expectCode(callback, code) {
  assert.throws(callback, (error) => (
    error instanceof WorkspaceRegistryError && error.code === code
  ));
}

test("registered alias resolves to its canonical real directory", (t) => {
  const fixture = createFixture(t);
  const workspace = fixture.registry.resolve("cyberboss");
  assert.equal(workspace.alias, "cyberboss");
  assert.equal(workspace.root, fs.realpathSync(fixture.workspaceRoot));
  assert.equal(workspace.repo, "LinzeColin/MetaDatabase");
  assert.equal(workspace.maxBytes, 4_294_967_296);
});

test("absolute path and unknown alias are rejected without filesystem changes", (t) => {
  const fixture = createFixture(t);
  const before = treeSnapshot(fixture.root);
  expectCode(() => fixture.registry.resolve("/etc"), "workspace_alias_invalid");
  expectCode(() => fixture.registry.resolve("unknown"), "workspace_alias_unknown");
  assert.deepEqual(treeSnapshot(fixture.root), before);
});

test("workspace root symlink escape is rejected", (t) => {
  const fixture = createFixture(t, { withEscape: true });
  expectCode(() => fixture.registry.resolve("cyberboss"), "workspace_symlink_rejected");
});

test("registry config symlink is rejected", (t) => {
  const fixture = createFixture(t);
  const link = path.join(fixture.root, "linked-workspaces.json");
  fs.symlinkSync(fixture.configPath, link);
  expectCode(
    () => new WorkspaceRegistry({ configPath: link, workspaceBase: fixture.base }),
    "workspace_config_symlink_rejected"
  );
});

test("workspace base symlink is rejected even when its target contains the root", (t) => {
  const fixture = createFixture(t);
  const linkedBase = path.join(fixture.root, "linked-base");
  fs.symlinkSync(fixture.base, linkedBase);
  const document = JSON.parse(fs.readFileSync(fixture.configPath, "utf8"));
  document.workspace_base = linkedBase;
  document.workspaces.cyberboss.root = path.join(linkedBase, "cyberboss");
  const configPath = path.join(fixture.root, "linked-base-workspaces.json");
  fs.writeFileSync(configPath, `${JSON.stringify(document, null, 2)}\n`);
  const registry = new WorkspaceRegistry({
    configPath,
    workspaceBase: linkedBase,
  });
  expectCode(
    () => registry.resolve("cyberboss"),
    "workspace_base_symlink_rejected"
  );
});

test("an unregistered real directory cannot enter Runtime dispatch", async (t) => {
  const fixture = createFixture(t);
  const app = Object.create(CyberbossApp.prototype);
  app.workspaceRegistry = fixture.registry;
  app.turnGateStore = {
    begin() {
      throw new Error("dispatch_must_not_begin");
    },
  };
  await assert.rejects(
    app.dispatchPreparedTurn({
      bindingKey: "binding",
      workspaceRoot: fixture.outside,
      prepared: {},
    }),
    (error) => error instanceof WorkspaceRegistryError
      && error.code === "workspace_root_not_allowlisted"
  );
});

test("/bind accepts the registered alias and stores only its canonical root", async (t) => {
  const fixture = createFixture(t);
  const sent = [];
  const stored = [];
  const app = Object.create(CyberbossApp.prototype);
  app.workspaceRegistry = fixture.registry;
  app.channelAdapter = {
    async sendText(message) {
      sent.push(message.text);
    },
  };
  app.runtimeAdapter = {
    getSessionStore() {
      return {
        buildBindingKey() {
          return "binding";
        },
        setActiveWorkspaceRoot(bindingKey, workspaceRoot) {
          stored.push([bindingKey, workspaceRoot]);
        },
      };
    },
  };
  const normalized = {
    workspaceId: "default",
    accountId: "account",
    senderId: "owner",
    contextToken: "context",
  };

  await app.handleBindCommand(normalized, { args: "cyberboss" });

  assert.deepEqual(stored, [["binding", fs.realpathSync(fixture.workspaceRoot)]]);
  assert.deepEqual(sent, ["✅ Workspace bound\nworkspace: cyberboss"]);
});

test("/bind rejects /etc and unknown aliases without changing a binding", async (t) => {
  const fixture = createFixture(t);
  const sent = [];
  let bindingWrites = 0;
  const app = Object.create(CyberbossApp.prototype);
  app.workspaceRegistry = fixture.registry;
  app.channelAdapter = {
    async sendText(message) {
      sent.push(message.text);
    },
  };
  app.runtimeAdapter = {
    getSessionStore() {
      return {
        buildBindingKey() {
          return "binding";
        },
        setActiveWorkspaceRoot() {
          bindingWrites += 1;
        },
      };
    },
  };
  const normalized = {
    workspaceId: "default",
    accountId: "account",
    senderId: "owner",
    contextToken: "context",
  };

  await app.handleBindCommand(normalized, { args: "/etc" });
  await app.handleBindCommand(normalized, { args: "unknown" });

  assert.equal(bindingWrites, 0);
  assert.match(sent[0], /workspace_alias_invalid/);
  assert.match(sent[1], /workspace_alias_unknown/);
});

test("readConfig derives workspaceRoot from the registry and rejects mismatched root", (t) => {
  const fixture = createFixture(t);
  const previousArgv = process.argv;
  const previousEnv = { ...process.env };
  t.after(() => {
    process.argv = previousArgv;
    process.env = previousEnv;
  });
  process.argv = [process.execPath, "cyberboss", "doctor"];
  process.env.CYBERBOSS_WORKSPACE_CONFIG = fixture.configPath;
  process.env.CYBERBOSS_WORKSPACE_BASE = fixture.base;
  process.env.CYBERBOSS_WORKSPACE_ALIAS = "cyberboss";
  delete process.env.CYBERBOSS_WORKSPACE_ROOT;

  const config = readConfig();
  assert.equal(config.workspaceAlias, "cyberboss");
  assert.equal(config.workspaceRoot, fs.realpathSync(fixture.workspaceRoot));

  process.env.CYBERBOSS_WORKSPACE_ROOT = fixture.outside;
  expectCode(() => readConfig(), "workspace_root_not_allowlisted");
});
