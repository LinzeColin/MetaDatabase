import test from "node:test";
import assert from "node:assert/strict";
import { createPlatformApp } from "../../service/platform/app.mjs";
import { testPlatform } from "./helpers.mjs";

const KEY = `wrk-${"W".repeat(32)}`;

test("微信读书同步快速入队、密钥不进入任务记录，并由工作器完成长任务", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerWeRead({ key: KEY, displayName: "后台同步用户" }, {}, { verify: false });
  const app = createPlatformApp({ service: platform.service, config: platform.config });
  const headers = {
    "content-type": "application/json",
    origin: platform.config.baseUrl,
    "sec-fetch-site": "same-origin",
    "x-wrp-internal-secret": platform.config.internalProxySecret,
    "x-csrf-token": user.session.csrf,
    cookie: `wrp_session=${user.session.token}`,
    "idempotency-key": "weread-async-job-1",
  };
  const queued = await app(new Request(`${platform.config.baseUrl}/v1/weread/sync`, {
    method: "POST", headers, body: JSON.stringify({ mode: "full", recommendationPages: 2 }),
  }));
  assert.equal(queued.status, 202);
  const job = (await queued.json()).job;
  assert.equal(job.provider, "weread");
  assert.equal(job.state, "PENDING");
  const duplicate = platform.service.createWeReadSyncJob(user.account.id, { mode: "auto" }, "weread-async-job-2");
  assert.equal(duplicate.id, job.id, "同一账户只能有一个活跃的微信读书同步任务");
  const raw = platform.store.db.prepare("SELECT selection_json AS selectionJson,selection_encrypted AS selectionEncrypted FROM import_jobs WHERE id=?").get(job.id);
  assert.equal(raw.selectionJson, "{}");
  assert.equal(JSON.stringify(raw).includes(KEY), false, "任务记录不能保存微信读书密钥");

  let captured;
  platform.service.syncWeRead = async (accountId, input) => {
    captured = { accountId, input };
    return {
      summary: {
        syncMode: "full", notebookBooks: 7, updatedDocuments: 5, unchangedDocuments: 2,
        skippedUnchangedBooks: 0, partial: false, failedCalls: 0,
        coverage: { verified: true, unresolvedDocuments: 0 },
      },
      failures: [],
    };
  };
  const complete = await platform.service.processNextImportJob("weread-job-worker");
  assert.equal(complete.state, "COMPLETE");
  assert.deepEqual(captured, { accountId: user.account.id, input: { mode: "full", recommendationPages: 2 } });
  assert.deepEqual(complete.progress.coverage, { verified: true, unresolvedDocuments: 0 });

  const status = await app(new Request(`${platform.config.baseUrl}/v1/weread/sync/${job.id}`, { headers: { ...headers, "x-csrf-token": undefined } }));
  assert.equal(status.status, 200);
  assert.equal((await status.json()).job.state, "COMPLETE");
});
