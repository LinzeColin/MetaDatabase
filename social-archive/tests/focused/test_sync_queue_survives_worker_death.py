"""同步跑到一半 service worker 被杀掉，任务不能就此消失（v0.0.0.7 / T15）。

## 为什么需要这组判据

MV3 的 service worker **空闲约 30 秒就被回收**。这不是异常，是常态。
一次同步跑几十秒到几分钟，中途被杀是必然会发生的事。

复现出来的症状：点了同步 → 转圈 → 永远不结束。
服务端那次 run 一直停在 `queued`，队列里也没有这条任务，
再点一次还是一样。用户唯一能看到的就是「在转」。

三个原因叠在一起：

  1. `processSyncQueue` 先 `queue.shift()` 把条目取出来并**持久化**，
     然后才去干活。worker 死在干活途中，这条任务就彻底没了。
  2. 锁写进 storage 但没有归属信息，判据是「两小时内算别人在跑」。
     持锁的 worker 已经死了，锁还在，接下来两小时点什么都是 busy。
  3. 闹钟是一次性的（只有 delayInMinutes），靠 `finally` 排下一次。
     worker 被杀时 `finally` 不执行 —— **再没有任何东西会唤醒它**。

## 判据打在哪

不打在源码文本上（那种判据我改一次实现就会假红/假绿），
而是**把 background.js 真的加载进 Node，用假的 chrome.* 跑一遍，
中途把 worker "杀掉"（丢弃全局环境、重新加载模块），
再看队列和锁还在不在**。storage 用一个跨 worker 存活的对象模拟，
这正是真实情况：chrome.storage.local 活得比 worker 久。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = ROOT / "apps/browser-extension/background.js"


def _node(script: str) -> object:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT, check=False, text=True, capture_output=True,
    )
    # 不用 check=True：它抛的 CalledProcessError 会把整段脚本打进错误信息，
    # 而真正需要看的 node 报错反而被埋掉。判据失败时要一眼看见原因。
    if completed.returncode != 0:
        raise AssertionError(f"node 退出码 {completed.returncode}：\n{completed.stderr.strip()[-2000:]}")
    return json.loads(completed.stdout or "null")


# 一个够用的 chrome.* 假件。storage 存在外面，**故意让它比 worker 活得久**。
HARNESS = r"""
import fs from 'node:fs';
import vm from 'node:vm';

const SOURCE = fs.readFileSync('apps/browser-extension/background.js', 'utf8');

function makeChrome(storage, alarms, hooks) {
  const listeners = {};
  const noop = () => {};
  const evt = () => ({ addListener: noop, removeListener: noop, hasListener: () => false });
  return {
    storage: { local: {
      async get(defaults) {
        const out = {};
        for (const [k, v] of Object.entries(defaults || {})) {
          out[k] = Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : v;
        }
        return out;
      },
      async set(obj) { Object.assign(storage, JSON.parse(JSON.stringify(obj))); },
      async remove(key) { delete storage[key]; },
    }, session: { get: async () => ({}), set: async () => {}, remove: async () => {} } },
    alarms: {
      async create(name, opts) { alarms[name] = opts; },
      async clear(name) { delete alarms[name]; return true; },
      onAlarm: evt(),
    },
    runtime: { onInstalled: evt(), onStartup: evt(), onMessage: evt(), onConnect: evt(),
               getURL: p => p, id: 'test', lastError: null, getManifest: () => ({ version: '0.0.0.7' }) },
    tabs: { onUpdated: evt(), onRemoved: evt(), query: async () => [], create: async () => ({ id: 1 }),
            sendMessage: async () => ({}), get: async () => ({ id: 1, url: '' }) },
    // **这个假 chrome 扮的是 service worker，就得像 service worker 一样抛。**
    //
    // 原来是 `request: async () => true`——夹具把用户必须自己挣的那一下
    // 直接给了。真 Chrome 的 service worker 里没有用户手势，
    // `chrome.permissions.request` **一定**抛这句话，即使权限刚被授予过
    // （evidence/G3/SHIPPED_PACKAGE.json 的
    // permission_request_from_service_worker 三项全是它）。
    //
    // 代价很具体：`connectChromeBookmarks` 里那行裸 request 在真浏览器里
    // 让「连接 Chrome 书签」整条抛出去，而**1266 条测试全绿**，
    // 因为它们看到的是这个 `() => true`。
    permissions: {
      onAdded: evt(), contains: async () => true,
      request: async () => { throw new Error('This function must be called during a user gesture'); },
    },
    bookmarks: null, commands: { onCommand: evt() },
    contextMenus: { onClicked: evt(), removeAll: (cb) => cb && cb(), create: noop },
    sidePanel: { setPanelBehavior: async () => {} },
    action: { setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}, setTitle: async () => {} },
    scripting: { executeScript: async () => [{ result: null }] },
    cookies: { getAll: async () => [] },
    notifications: { create: noop },
    ...hooks,
  };
}

// 把 background.js 当一个 worker 实例加载。返回它的内部函数。
export function bootWorker(storage, alarms, { syncImpl, onFetch } = {}) {
  const chrome = makeChrome(storage, alarms, {});
  // 在 fetch 这一层假装服务端。
  // **不能改 SA.api**——它是冻结的（`Cannot assign to read only property`），
  // 那是对的：真身不该被随便换掉。所以判据从更底下的 fetch 进去。
  const fetchStub = async (url, opts = {}) => {
    const decided = onFetch ? onFetch(String(url), opts) : null;
    if (decided && decided.__throw) throw new Error(decided.__throw);
    return new Response(JSON.stringify(decided === null || decided === undefined ? { items: [] } : decided),
      { status: (decided && decided.__status) || 200, headers: { 'content-type': 'application/json' } });
  };
  const sandbox = { chrome, console, fetch: fetchStub,
                    Headers, Request, Response, AbortController, FormData, Blob,
                    setTimeout, clearTimeout, setInterval, clearInterval, URL, URLSearchParams,
                    TextEncoder, TextDecoder, atob, btoa,
                    crypto: { randomUUID: () => 'uuid-' + Math.random().toString(36).slice(2) } };
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  vm.createContext(sandbox);

  // background.js 顶部用 importScripts 加载同伴模块；这里给个能用的替身。
  sandbox.importScripts = (...files) => {
    for (const f of files) {
      const p = 'apps/browser-extension/' + f;
      if (fs.existsSync(p)) vm.runInContext(fs.readFileSync(p, 'utf8'), sandbox, { filename: f });
    }
  };
  vm.runInContext(SOURCE, sandbox, { filename: 'background.js' });
  if (syncImpl) sandbox.syncAccountById = syncImpl(sandbox);
  return sandbox;
}
"""


def _script(body: str) -> str:
    return (
        "import fs from 'node:fs';\n"
        "fs.writeFileSync(process.env.TMPDIR + '/sa_harness.mjs', " + json.dumps(HARNESS) + ");\n"
        "const { bootWorker } = await import(process.env.TMPDIR + '/sa_harness.mjs');\n"
        + body
    )


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_worker_killed_mid_sync_does_not_lose_the_queued_task() -> None:
    """核心判据：worker 死在同步途中，任务必须还在队列里。

    这条判据红的时候，用户看到的就是「点了同步，永远在转」。
    """
    result = _node(_script(r"""
    const storage = {}, alarms = {};

    // ── 第一个 worker：跑到一半被杀 ──
    const w1 = bootWorker(storage, alarms);
    await w1.enqueueAccountSync({ accountId: 'acct-1', syncRunId: 'run-1' });
    const queuedBefore = (storage['saAccountSyncQueue'] || []).length;

    // syncAccountById 永不返回 —— 模拟"跑到一半"
    w1.syncAccountById = () => new Promise(() => {});
    w1.processSyncQueue().catch(() => {});
    await new Promise(r => setTimeout(r, 60));   // 让它跑到设置锁那一步

    const lockedBy = storage['saAccountSyncQueueLock'];
    const queueDuringRun = storage['saAccountSyncQueue'] || [];

    // ── worker 被杀：丢弃 w1，storage 留下 ──
    // ── 第二个 worker 起来（周期闹钟把它拉起来的）──
    const w2 = bootWorker(storage, alarms);
    await w2.reclaimAbandonedSyncWork();
    const queueAfterRecovery = storage['saAccountSyncQueue'] || [];

    console.log(JSON.stringify({
      queuedBefore,
      queueDuringRun: queueDuringRun.length,
      lockHeld: !!lockedBy,
      queueAfterRecovery: queueAfterRecovery.length,
      lockAfterRecovery: !!storage['saAccountSyncQueueLock'],
      itemIsRunnableAgain: queueAfterRecovery.some(i => i.accountId === 'acct-1' && !i.startedAt),
      alarmIsPeriodic: !!(alarms['sa-account-sync-queue'] || {}).periodInMinutes,
    }));
    """))

    assert result["queuedBefore"] == 1
    assert result["queueDuringRun"] == 1, (
        "干活期间条目就已经不在队列里了——worker 一死这条任务就永远消失"
    )
    assert result["lockHeld"], "锁没设上，判据前提不成立"
    assert result["queueAfterRecovery"] == 1, "worker 死后任务丢了"
    assert result["itemIsRunnableAgain"], "任务还留着在跑标记，没人会再碰它"
    assert not result["lockAfterRecovery"], (
        "死掉的 worker 留下的锁没被回收——接下来点什么都是 busy"
    )
    assert result["alarmIsPeriodic"], (
        "闹钟是一次性的：worker 被杀时 finally 不执行，再没有东西会唤醒它"
    )


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_giving_up_after_repeated_interruption_is_explicit_not_silent() -> None:
    """反复被打断到顶之后，必须**说出来**，不能从队列里安静消失。

    安静消失的后果正是这一版要消灭的东西：用户看到一次没有解释的 0 条。
    """
    result = _node(_script(r"""
    const storage = {}, alarms = {};
    // 伪造一条"已经被打断过 MAX 次"的在跑条目，且它的 worker 已经不在了
    storage['saAccountSyncQueue'] = [{
      accountId: 'acct-1', syncRunId: 'run-1', attempts: 3,
      startedAt: Date.now() - 60000, workerId: 'a-worker-that-is-gone',
      enqueuedAt: Date.now() - 120000, updatedAt: Date.now() - 60000,
    }];
    storage['saAccountSyncQueueLock'] = { accountId: 'acct-1', startedAt: Date.now() - 60000, workerId: 'a-worker-that-is-gone' };

    const w = bootWorker(storage, alarms);
    await w.reclaimAbandonedSyncWork();

    const last = storage['saAccountSyncQueueLastResult'] || null;
    console.log(JSON.stringify({
      queueLength: (storage['saAccountSyncQueue'] || []).length,
      lockCleared: !storage['saAccountSyncQueueLock'],
      reported: !!last,
      ok: last ? last.ok : null,
      failureCode: last ? last.failureCode : null,
      messageIsChinese: last ? /[一-龥]/.test(String(last.error || '')) : false,
      messageHasNoStack: last ? !/\bat \w+|Error:/.test(String(last.error || '')) : false,
    }));
    """))

    assert result["queueLength"] == 0, "到顶了还留在队列里，会被无限重试"
    assert result["lockCleared"], "死掉的 worker 的锁没清"
    assert result["reported"], (
        "任务被放弃了，但没有留下任何结果——用户看到的就是一次没有解释的 0 条"
    )
    assert result["ok"] is False, "放弃却报成功"
    assert result["failureCode"] == "SYNC_INTERRUPTED"
    assert result["messageIsChinese"], "给人看的提示不是中文"
    assert result["messageHasNoStack"], "把堆栈/英文错误摆给用户看了"


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_a_live_workers_own_lock_is_not_stolen() -> None:
    """回收判据不能矫枉过正：**本 worker 自己**持的锁必须留着。

    否则两个 processSyncQueue 会同时进去，同一个账号被同步两遍。
    """
    result = _node(_script(r"""
    const storage = {}, alarms = {};
    const w = bootWorker(storage, alarms);
    w.syncAccountById = () => new Promise(() => {});   // 卡住不返回
    await w.enqueueAccountSync({ accountId: 'acct-1', syncRunId: 'run-1' });
    w.processSyncQueue().catch(() => {});
    await new Promise(r => setTimeout(r, 60));

    const lockBefore = storage['saAccountSyncQueueLock'];
    // 同一个 worker 再进一次：必须被挡住，而且不许把自己的锁回收掉
    const second = await w.processSyncQueue();
    console.log(JSON.stringify({
      lockSurvived: !!storage['saAccountSyncQueueLock'],
      sameLock: JSON.stringify(lockBefore) === JSON.stringify(storage['saAccountSyncQueueLock']),
      secondState: second.state,
    }));
    """))

    assert result["lockSurvived"], "把自己正在用的锁回收了"
    assert result["sameLock"], "锁被改写了"
    assert result["secondState"] == "busy", (
        f"同一个 worker 第二次进去没被挡住（state={result['secondState']}）——会同步两遍"
    )


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_giving_up_tells_the_server_so_the_run_leaves_queued() -> None:
    """放弃时必须报服务端，否则那次 run 永远停在 queued，界面永远转圈。

    这是「点了同步永远不结束」真正被用户看见的那一半：
    扩展这边收拾干净了没用，服务端的 sync_run 才是界面读的东西。
    """
    result = _node(_script(r"""
    const storage = {}, alarms = {};
    storage['saAccountSyncQueue'] = [{
      accountId: 'acct-1', syncRunId: 'run-1', attempts: 3,
      startedAt: Date.now() - 60000, workerId: 'a-worker-that-is-gone',
    }];

    const posted = [];
    const w = bootWorker(storage, alarms, { onFetch: (url, opts) => {
      if (url.includes('/batches')) {
        posted.push({ path: url, body: JSON.parse(opts.body || '{}') });
        return { sync_run_id: 'run-1', status: 'failed' };
      }
      // Chrome 书签账号：平台是 generic-web，**平台目录里没有这一条**。
      // 关系类型只能从 run 自己身上拿。
      if (url.includes('/v1/sync-runs/run-1')) return { id: 'run-1', status: 'queued', relation_scope: ['bookmark'] };
      if (url.includes('/v1/accounts')) return { items: [{ id: 'acct-1', platform: 'generic-web' }] };
      return { items: [] };
    } });
    // **不再手动调 reclaim**：background.js 顶层在 worker 启动时就会自己跑一次。
    // 那才是真实路径——周期闹钟把 worker 拉起来，恢复就该自动发生。
    // 手动再调一次反而会和顶层那次抢队列，测出来的是假象。
    await new Promise(r => setTimeout(r, 80));

    const batch = posted.length ? posted[0].body : null;
    console.log(JSON.stringify({
      posted: posted.length,
      path: posted.length ? posted[0].path : null,
      scopeType: batch ? batch.scope_type : null,
      completeness: batch ? batch.completeness : null,
      failureCode: batch ? batch.failure_code : null,
      hasMore: batch ? batch.has_more : null,
      itemCount: batch ? (batch.items || []).length : null,
      relationType: batch ? batch.relation_type : null,
    }));
    """))

    assert result["posted"] == 1, (
        "放弃时没有通知服务端——那次 run 会永远停在 queued，界面永远转圈"
    )
    assert "/batches" in (result["path"] or "")
    assert result["scopeType"] == "relation", "不是关系终批，服务端不会把这次 run 落终态"
    assert result["completeness"] == "failed"
    assert result["failureCode"] == "SYNC_INTERRUPTED"
    assert result["hasMore"] is False
    assert result["itemCount"] == 0
    assert result["relationType"] == "bookmark", (
        "关系类型不是从 run 自己身上取的——Chrome 书签的平台 generic-web "
        "不在平台目录里，靠平台去猜就会漏掉最常用的那个账号"
    )


@pytest.mark.skipif(not BACKGROUND.is_file(), reason="background.js 不存在")
def test_failing_to_reach_the_server_does_not_break_local_recovery() -> None:
    """上报失败（离线／run 已终态）不能反过来把队列恢复弄挂。"""
    result = _node(_script(r"""
    const storage = {}, alarms = {};
    storage['saAccountSyncQueue'] = [{
      accountId: 'acct-1', syncRunId: 'run-1', attempts: 3,
      startedAt: Date.now() - 60000, workerId: 'gone',
    }];
    let unhandled = null;
    process.on('unhandledRejection', e => { unhandled = String(e && e.message || e); });
    const w = bootWorker(storage, alarms, { onFetch: () => ({ __throw: 'offline' }) });
    await new Promise(r => setTimeout(r, 80));
    const threw = unhandled;
    console.log(JSON.stringify({
      threw,
      queueLength: (storage['saAccountSyncQueue'] || []).length,
      recordedLocally: !!storage['saAccountSyncQueueLastResult'],
    }));
    """))

    assert result["threw"] is None, f"上报失败把恢复流程弄挂了：{result['threw']}"
    assert result["queueLength"] == 0, "队列没收拾干净"
    assert result["recordedLocally"], "本地连一笔记录都没留下"
