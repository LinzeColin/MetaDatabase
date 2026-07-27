import test from "node:test";
import assert from "node:assert/strict";
import { fetchWithPolicy } from "../../service/platform/network.mjs";
import { testPlatform } from "./helpers.mjs";

const PASSWORD = "Correct-Horse-2026";

test("统一上游策略对 GET 有界重试、对非幂等 POST 不自动重试并禁用自动重定向", async () => {
  let getCalls = 0;
  const observedRedirects = [];
  const fetchImpl = async (_url, init) => {
    observedRedirects.push(init.redirect);
    getCalls += 1;
    if (getCalls === 1) return new Response("temporary", { status: 503 });
    return new Response("ok", { status: 200 });
  };
  const response = await fetchWithPolicy(fetchImpl, "https://provider.example.test/data", { method: "GET" }, { timeoutMs: 100, attempts: 2, maxRetryDelayMs: 0 });
  assert.equal(response.status, 200);
  assert.equal(getCalls, 2);
  assert.deepEqual(observedRedirects, ["manual", "manual"]);

  let postCalls = 0;
  const post = await fetchWithPolicy(async () => {
    postCalls += 1;
    return new Response("temporary", { status: 503 });
  }, "https://provider.example.test/token", { method: "POST", body: "code=one" }, { timeoutMs: 100, attempts: 3 });
  assert.equal(post.status, 503);
  assert.equal(postCalls, 1);
});

test("统一上游策略在有限超时后终止，不等待真实时间窗口", async () => {
  await assert.rejects(
    () => fetchWithPolicy((_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(init.signal.reason), { once: true });
    }), "https://provider.example.test/slow", { method: "GET" }, { timeoutMs: 20, attempts: 1 }),
    error => error.code === "UPSTREAM_TIMEOUT" || /超时/u.test(error.message),
  );
});

test("导入租约过期后可被另一 worker 安全回收，心跳按阈值变为不健康", async t => {
  let now = 1_700_000_000_000;
  const platform = testPlatform({ clock: () => now });
  t.after(platform.close);
  const user = await platform.service.registerPassword({ email: "lease@example.com", password: PASSWORD });
  const job = platform.service.createImportJob(user.account.id, "obsidian", { items: [{ name: "one.md", path: "Vault/one.md", content: "租约正文" }] }, "lease-operation");
  const first = platform.store.claimNextImportJob("worker-a", 5);
  assert.equal(first.id, job.id);
  assert.equal(first.workerId, "worker-a");
  assert.equal(first.attempts, 1);
  assert.equal(platform.store.claimNextImportJob("worker-b", 5), null);

  platform.store.heartbeat("worker-a", "import", "v0.0.0.1.8");
  assert.equal(platform.store.workerHealth("import", 30).ok, true);
  now += 6_000;
  const reclaimed = platform.store.claimNextImportJob("worker-b", 5);
  assert.equal(reclaimed.id, job.id);
  assert.equal(reclaimed.workerId, "worker-b");
  assert.equal(reclaimed.attempts, 2);
  now += 31_000;
  assert.equal(platform.store.workerHealth("import", 30).ok, false);
});
