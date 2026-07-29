import test from "node:test";
import assert from "node:assert/strict";
import { access, mkdtemp, rm } from "node:fs/promises";
import { execFile as execFileCallback } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { loadConfig } from "../../service/platform/config.mjs";
import { testPlatform, testConfig } from "./helpers.mjs";

const execFile = promisify(execFileCallback);

function productionEnv(overrides = {}) {
  const secret = Buffer.alloc(32, 31).toString("base64");
  return {
    NODE_ENV: "production",
    WRP_PUBLIC_BASE_URL: "https://weread.linzezhang.com",
    WRP_SESSION_PEPPER: secret,
    WRP_CREDENTIAL_PEPPER: Buffer.alloc(32, 29).toString("base64"),
    WRP_KEYRING_JSON: JSON.stringify({ k1: Buffer.alloc(32, 27).toString("base64") }),
    WRP_ACTIVE_KEY_ID: "k1",
    WRP_INTERNAL_PROXY_SECRET: "production-like-test-secret-without-real-value",
    WRP_TASKPACK_VERSION: "v0.0.0.1.9",
    WRP_RELEASE_COMMIT: "0123456789abcdef0123456789abcdef01234567",
    WRP_OVH_RELEASE_ID: "ovh-release-test",
    WRP_SITES_PROJECT_ID: "sites-project-test",
    WRP_OBJECT_STORE_MODE: "r2",
    WRP_R2_ENDPOINT: "https://r2.cloudflarestorage.com",
    WRP_R2_BUCKET: "weread-port-test",
    WRP_R2_ACCESS_KEY_ID: "test-access-key",
    WRP_R2_SECRET_ACCESS_KEY: "test-secret-key",
    WRP_GOOGLE_CLIENT_ID: "google-client",
    WRP_GOOGLE_CLIENT_SECRET: "google-secret",
    WRP_GITHUB_CLIENT_ID: "github-client",
    WRP_GITHUB_CLIENT_SECRET: "github-secret",
    WRP_NOTION_CLIENT_ID: "notion-client",
    WRP_NOTION_CLIENT_SECRET: "notion-secret",
    ...overrides,
  };
}

test("生产配置缺少部署身份时 fail-closed", () => {
  assert.throws(() => loadConfig(productionEnv({ WRP_RELEASE_COMMIT: "" })), /部署身份/);
  assert.throws(() => loadConfig(productionEnv({ WRP_TASKPACK_VERSION: "v0.0.0.1.8" })), /冻结版本/);
});

test("R2 主对象与 Private-Database 冷备使用隔离命名空间", () => {
  const config = loadConfig(productionEnv());
  assert.equal(config.primaryObjectPrefix, "primary-objects");
  assert.equal(config.privateDatabaseBackupPrefix, "backups/private-database");
  assert.throws(() => loadConfig(productionEnv({ WRP_PRIVATE_DATABASE_BACKUP_PREFIX: "primary-objects" })), /命名空间必须隔离/);
});

test("账户正文对象只写入 primary-objects 并在 readiness 暴露精确 release identity", async t => {
  const config = testConfig({
    primaryObjectPrefix: "primary-objects",
    privateDatabaseBackupPrefix: "backups/private-database",
    releaseIdentity: { taskpackVersion: "v0.0.0.1.9", releaseCommit: "test-release-commit", ovhReleaseId: "test-ovh-release", sitesProjectId: "test-sites-project" },
  });
  const platform = testPlatform({ config });
  t.after(platform.close);
  platform.store.heartbeat("test-worker", "import", "v0.0.0.1.9");
  const user = await platform.service.registerPassword({ email: "release-test@linzezhang.com", password: "StrongPassword9!", displayName: "版本验收" });
  const note = await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "release", title: "版本", content: "部署身份测试" });
  const row = platform.store.getNote(user.account.id, note.id);
  assert.match(row.objectKey, /^primary-objects\/accounts\//);
  const readiness = await platform.service.readiness({ force: true });
  assert.equal(readiness.releaseIdentity.taskpackVersion, "v0.0.0.1.9");
  assert.equal(readiness.dependencies.objectNamespaces.ok, true);
});

test("不可变账户发布包携带服务依赖的共享微信读书规范化模块", async t => {
  const root = await mkdtemp(path.join(tmpdir(), "weread-release-package-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const commit = "a".repeat(40);
  const install = fileURLToPath(new URL("../../service/install_platform.py", import.meta.url));
  await execFile("python3", [install, "--root", root, "--release-commit", commit, "--ovh-release-id", "test-release", "--sites-project-id", "test-sites"]);
  const release = path.join(root, "opt", "weread-port", "releases", `0.0.0.1.9-${commit.slice(0, 12)}-test-release`);
  const normalizer = path.join(release, "src", "core", "normalize.js");
  await access(normalizer);
  await execFile(process.execPath, ["--input-type=module", "--eval", `import(${JSON.stringify(pathToFileURL(path.join(release, "service", "platform", "weread.mjs")).href)})`]);
});
