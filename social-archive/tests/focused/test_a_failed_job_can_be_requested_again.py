"""失败过的活儿要能被重新请求（v0.0.0.7 / INV-NO-SILENT-ZERO）。

`enqueue_job` 用 (job_type, connector_id, payload) 的稳定哈希当 job_id，
配 `INSERT OR IGNORE`。对**还没跑完**的活儿这是对的：同一件事不该排两次。

但一条 `status='failed'` 的记录会把这件事**永久钉死**：之后每一次 enqueue
都被 IGNORE 掉，接口照样返回 job_id 和 202，界面照样说「已加入队列」，
而**没有任何东西会跑**。

2026-08-04 生产实测：markdown 导出的根因修好之后，我重排了 83 条，
79 条跑完了，剩下 4 条纹丝不动——它们在 2026-08-03T17:23 失败过，
job 表里那一行从那时起就没再动过，接口返回的是那 4 个旧 id。
"""

from social_archive.db import RuntimeStore

# conftest.py 里已经有 store fixture（RuntimeStore(settings.runtime_db) + initialize），
# 直接用它，不要在这里再造一个——我第一版自己 new 了一个并且把参数传错了。


def _status(store: RuntimeStore, job_id: str) -> str:
    with store.connection() as con:
        return con.execute("SELECT status FROM job WHERE id=?", (job_id,)).fetchone()["status"]


def test_re_enqueueing_a_failed_job_puts_it_back_in_the_queue(store) -> None:
    job_id = store.enqueue_job("export_destination", {"content_id": "cnt_x", "destination_id": "markdown"})
    store.finish_job(job_id, success=False, error_code="OSERROR", error_message="File name too long")
    assert _status(store, job_id) == "failed"

    again = store.enqueue_job("export_destination", {"content_id": "cnt_x", "destination_id": "markdown"})
    assert again == job_id, "同一件事应当还是同一个 id"
    assert _status(store, job_id) == "queued", (
        "失败过的活儿被永久钉死了——接口会返回 202，而什么都不会跑"
    )


def test_a_revived_job_is_actually_claimable(store) -> None:
    """回到 queued 还不够，得真的能被 worker 领走。"""
    job_id = store.enqueue_job("export_destination", {"content_id": "cnt_y", "destination_id": "markdown"})
    store.finish_job(job_id, success=False, error_code="OSERROR", error_message="boom")
    store.enqueue_job("export_destination", {"content_id": "cnt_y", "destination_id": "markdown"})
    claimed = store.claim_job("worker-test")
    assert claimed is not None and claimed["id"] == job_id, "复活了却领不走，等于没复活"


def test_a_finished_job_is_not_silently_re_run(store) -> None:
    """**只复活 failed。** 把已经做完的活儿因为一次重复入队就重跑，是另一种意外。"""
    job_id = store.enqueue_job("export_destination", {"content_id": "cnt_z", "destination_id": "markdown"})
    store.finish_job(job_id, success=True)
    done_status = _status(store, job_id)
    store.enqueue_job("export_destination", {"content_id": "cnt_z", "destination_id": "markdown"})
    assert _status(store, job_id) == done_status, "已完成的活儿被重复入队顶回去重跑了"


def test_a_queued_job_is_not_disturbed(store) -> None:
    job_id = store.enqueue_job("export_destination", {"content_id": "cnt_q", "destination_id": "markdown"})
    assert _status(store, job_id) == "queued"
    store.enqueue_job("export_destination", {"content_id": "cnt_q", "destination_id": "markdown"})
    assert _status(store, job_id) == "queued"
