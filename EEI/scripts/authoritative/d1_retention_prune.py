#!/usr/bin/env python3
"""D1 发布面保留期守卫 —— 定时释放存储，永远不升级付费。

设计约束（都是 2026-09-02/03 实测出来的，不是推测）：

1. D1 免费档**每日写入行数和读取行数都是硬拦的**，超了直接 400
   `... exceeded D1's free tier daily row write/read limit ... wait until
   tomorrow (midnight UTC)`。所以清理必须「每晚啃一段，撞配额就收工，明晚续」。
2. D1 不允许 `VACUUM`（`cannot VACUUM from within a transaction`），
   但**删除后 Cloudflare 会自己回收空间** —— 实测 499.1MB -> 192.8MB。
3. 配额是**账号级**的，adp-mirror 和本清理抢同一份。

v2 修的缺陷（v1 在 2026-09-03 那轮暴露）：
  v1 的循环只有超时条件，没有「已经删空」的条件。收敛之后它继续空转了
  30 分钟、跑了 4706 个空批，把当日**读**额度烧光，于是超限邮件照发。
  而且 v1 每批把 `SELECT id ... LIMIT` 子查询嵌进三条 DELETE 里，
  同一次扫描做了三遍；它报出的「删了 705 万条」也是假的 —— 那只是
  批次数 x 批大小，跟真实删除量无关。

  v2：先 SELECT 出这一批的真实 id，**空结果就是收敛信号，立刻停**；
  再用字面 id 列表删三张表 —— 扫描一次，计数真实。
"""
import json, os, sys, time
sys.path.insert(0, "/app")
from scripts.publish_to_cloud_channel import WorkerApiTransport

KEEP_FROM   = os.environ.get("EEI_D1_KEEP_FROM", "2025-01-01")[:4]
BATCH       = int(os.environ.get("EEI_D1_PRUNE_BATCH", "1000"))
MAX_BATCHES = int(os.environ.get("EEI_D1_PRUNE_MAX_BATCHES", "800"))
MAX_SECONDS = int(os.environ.get("EEI_D1_PRUNE_MAX_SECONDS", "1500"))
STATE       = os.environ.get("EEI_D1_PRUNE_STATE", "/state/.d1_prune_state.json")
EXPR        = "COALESCE(announced_at, effective_at, observed_at)"
# 写限和读限的报错文案都含这一段；两种都是「今天到此为止」，不是故障。
QUOTA_MARK  = "free tier daily row"


def load_state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(s: dict) -> None:
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE)
    except Exception as e:
        print(f"[prune] 状态写入失败(不致命): {e}", flush=True)


def sql_ids(rows) -> str:
    # id 是 uuid，但仍然转义单引号：不假设上游格式，字面量拼接必须自己保证安全
    return ",".join("'" + str(r["id"]).replace("'", "''") + "'" for r in rows)


def main() -> int:
    url = os.environ.get("EEI_PUBLISH_URL", "").strip()
    tok = os.environ.get("EEI_PUBLISH_TOKEN", "").strip()
    if not (url and tok):
        print("[prune] 缺 EEI_PUBLISH_URL/TOKEN，跳过")
        return 0

    started = time.time()
    st = load_state()
    st["runs"] = st.get("runs", 0) + 1
    st["last_started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    st["keep_from"] = KEEP_FROM

    select_sql = (
        f"SELECT id FROM events WHERE substr({EXPR},1,4) < '{KEEP_FROM}' "
        f"ORDER BY {EXPR} ASC LIMIT {BATCH}"
    )

    ch = WorkerApiTransport(url, tok)
    deleted = batches = 0
    converged = quota_hit = False
    err = None
    try:
        while batches < MAX_BATCHES and time.time() - started < MAX_SECONDS:
            try:
                res = ch.execute([select_sql])
                rows = (res[0].get("rows") if res else None) or []
            except Exception as e:
                msg = str(e)
                if QUOTA_MARK in msg:
                    quota_hit = True
                else:
                    err = msg[:300]
                break

            if not rows:
                # ★ v1 缺的就是这一条。删空了就必须停，否则每批都是一次全表扫描。
                converged = True
                break

            ids = sql_ids(rows)
            try:
                ch.execute([
                    f"DELETE FROM event_evidence WHERE event_id IN ({ids});",
                    f"DELETE FROM event_participants WHERE event_id IN ({ids});",
                    f"DELETE FROM events WHERE id IN ({ids});",
                ])
            except Exception as e:
                msg = str(e)
                if QUOTA_MARK in msg:
                    quota_hit = True
                else:
                    err = msg[:300]
                break

            deleted += len(rows)          # 真实删除条数，不是批次 x 批大小
            batches += 1
            if batches % 25 == 0:
                print(f"[prune] 已删 {deleted:,} 条 events ({batches} 批)", flush=True)
    finally:
        ch.close()

    st["last_batches"] = batches
    st["last_deleted"] = deleted
    st["total_deleted"] = st.get("total_deleted", 0) + deleted
    st["converged"] = converged
    st["last_quota_hit"] = quota_hit
    st["last_error"] = err
    st["last_finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # v1 写下的假计数留个墓碑，别让以后的人拿它当历史数据
    st.pop("last_deleted_estimate", None)
    st.pop("total_deleted_estimate", None)
    st["note"] = "v1(2026-09-02)的 *_estimate 字段是批次x批大小的虚数，已删除"
    save_state(st)

    if converged:
        tail = "已收敛：保留期之前没有 events 了"
    elif quota_hit:
        tail = "撞到当日配额，明晚续（预期收尾，不是失败）"
    elif err:
        tail = f"失败：{err}"
    else:
        tail = "达到本轮批次/时间上限，明晚续"
    print(f"[prune] 本轮真实删除 {deleted:,} 条 events（{batches} 批）；{tail}", flush=True)
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
