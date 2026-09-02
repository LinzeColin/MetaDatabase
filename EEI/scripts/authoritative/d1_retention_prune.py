#!/usr/bin/env python3
"""D1 发布面保留期守卫 —— 定时释放存储，永远不升级付费。

为什么必须是「每晚小口啃」而不是「一次删完」：
  D1 免费档的每日写入行数是**硬拦**的，超了直接
  `D1_ERROR: ... exceeded D1's free tier daily row write limit`，
  要等 UTC 零点才恢复。2026-09-02 实测：一次性删 31 个年份，
  删完 1994 就被拦死，剩下 30 个年份全 400。
  所以本脚本每晚跑，删到被拦为止，第二晚接着删，直到收敛到保留期。

为什么不 VACUUM：
  D1 不允许 —— `cannot VACUUM from within a transaction: SQLITE_ERROR`。
  删除只把页放回 freelist 供后续 INSERT 复用，file_size 不会变小。
  目标是「不再增长、不再撞 SQLITE_NOMEM」，不是把文件缩回去。

零 agent 零 token：纯脚本，不调任何模型。
"""
import json, os, sys, time
sys.path.insert(0, "/app")
from scripts.publish_to_cloud_channel import WorkerApiTransport

KEEP_FROM   = os.environ.get("EEI_D1_KEEP_FROM", "2025-01-01")[:4]
BATCH       = int(os.environ.get("EEI_D1_PRUNE_BATCH", "1500"))   # 每批删多少条 events
MAX_SECONDS = int(os.environ.get("EEI_D1_PRUNE_MAX_SECONDS", "1800"))
STATE       = os.environ.get("EEI_D1_PRUNE_STATE", "/state/.d1_prune_state.json")
EXPR        = "COALESCE(announced_at, effective_at, observed_at)"
QUOTA_MARK  = "daily row write limit"

def load_state():
    try:
        with open(STATE) as f: return json.load(f)
    except Exception:
        return {}

def save_state(s):
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f: json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE)
    except Exception as e:
        print(f"[prune] 状态写入失败(不致命): {e}", flush=True)

def main() -> int:
    url = os.environ.get("EEI_PUBLISH_URL", "").strip()
    tok = os.environ.get("EEI_PUBLISH_TOKEN", "").strip()
    if not (url and tok):
        print("[prune] 缺 EEI_PUBLISH_URL/TOKEN，跳过"); return 0

    started = time.time()
    st = load_state()
    st.setdefault("runs", 0)
    st["runs"] += 1
    st["last_started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    st["keep_from"] = KEEP_FROM

    # 目标批：保留期之前、最老的 BATCH 条。ORDER BY 保证每次啃最老的一段，
    # 中途被配额拦下也不会留下「删了子表没删主表」的悬挂行 —— 三条语句
    # 在同一个 apply_statements 里按 子→父 顺序发出。
    sel = (f"SELECT id FROM events WHERE substr({EXPR},1,4) < '{KEEP_FROM}' "
           f"ORDER BY {EXPR} ASC LIMIT {BATCH}")

    ch = WorkerApiTransport(url, tok)
    batches = quota_hit = 0
    err = None
    try:
        while time.time() - started < MAX_SECONDS:
            try:
                ch.apply_statements([
                    f"DELETE FROM event_evidence WHERE event_id IN ({sel});",
                    f"DELETE FROM event_participants WHERE event_id IN ({sel});",
                    f"DELETE FROM events WHERE id IN ({sel});",
                ])
            except Exception as e:
                msg = str(e)
                if QUOTA_MARK in msg:
                    quota_hit = 1
                    print(f"[prune] 撞到当日写入配额，本轮停在第 {batches} 批（正常，明晚续）", flush=True)
                else:
                    err = msg[:300]
                    print(f"[prune] 失败: {err}", flush=True)
                break
            batches += 1
            if batches % 10 == 0:
                print(f"[prune] 已删 {batches} 批 (~{batches*BATCH} 条 events)", flush=True)
    finally:
        ch.close()

    st["last_batches"] = batches
    st["last_deleted_estimate"] = batches * BATCH
    st["total_deleted_estimate"] = st.get("total_deleted_estimate", 0) + batches * BATCH
    st["last_quota_hit"] = bool(quota_hit)
    st["last_error"] = err
    st["last_finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(st)

    print(f"[prune] 本轮 {batches} 批, 约 {batches*BATCH} 条; "
          f"累计约 {st['total_deleted_estimate']} 条; 配额拦截={bool(quota_hit)}", flush=True)
    # 撞配额不是失败 —— 它是这个设计预期内的收尾方式
    return 1 if err else 0

if __name__ == "__main__":
    raise SystemExit(main())
