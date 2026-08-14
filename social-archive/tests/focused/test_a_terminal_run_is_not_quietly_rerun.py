"""已经结束的同步，不许被悄悄翻出来重跑一遍（v0.0.0.7 / T13）。

## 怎么找到的

`scripts/list_lists_that_almost_match.py` 报了一对 80% 像的清单：

    src/social_archive/db.py:1826       {"completed","partial","cancelled","failed","blocked_environment"}
    src/social_archive/account_sync.py  {"cancelled","completed","partial","failed"}

**后者少一个 `blocked_environment`。** 前者是「算不算跑完了」（跑完要盖
completed_at），后者是 `process_job` 开头那道「已经结束就别做了」的闸。

## 实测出来的后果

把一个 run 打到 `blocked_environment`（它已经盖了 completed_at）、
账号此刻仍然连着，再投一次同一个任务——**它真的往下跑到连接器去了**。

也就是说：一个已经报给用户「被环境挡住了」的运行，会被悄悄重跑一遍，
而用户从没点过重试。从阻塞里出来的正当路子是 db.py 的 retry 迁移
（`{partial, failed, blocked_environment} → queued`），那条路会把它重新排队。
"""

from __future__ import annotations

import pytest

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountSyncRequest

TERMINAL = ("cancelled", "completed", "partial", "failed", "blocked_environment")


def _blocked_run(store, service, settings, status: str):
    account_id = store.upsert_source_account(
        platform="reddit", external_account_id="owner", display_name="owner",
        auth_method="oauth", auth_handle_ref="conn_fixture", connection_state="connected")
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["saved"], trigger_type="first_connect"))
    run_id = started["sync_run_id"]
    store.update_sync_run(run_id, status=status, completeness="unknown",
                          error_code="ACCOUNT_REAUTH_REQUIRED")
    return coordinator, account_id, run_id


class _RegistryThatMustNotBeReached:
    def run(self, *args, **kwargs):
        raise AssertionError("**已经结束的运行被翻出来重跑了**——它跑到连接器去了")


@pytest.mark.parametrize("status", TERMINAL)
def test_no_terminal_status_gets_reprocessed(settings, store, service, status) -> None:
    """五个终态，一个都不许被重跑。

    **逐个参数化，不是只验 blocked_environment 那一个**：这次漏的是它，
    下次可能是别的。把整组钉住，加一个新终态时这里会提醒。
    """
    coordinator, account_id, run_id = _blocked_run(store, service, settings, status)
    coordinator.registry = _RegistryThatMustNotBeReached()
    coordinator.process_job({"sync_run_id": run_id, "account_id": account_id})
    assert store.get_sync_run(run_id)["status"] == status, (
        f"{status} 是终态，重投任务之后它被改成了别的"
    )


def test_the_two_terminal_lists_agree(settings, store, service) -> None:
    """**db.py 说「算跑完了」的那一组，process_job 也必须当成结束。**

    两处各写各的必然漂开——这一条就是那次漂开留下的。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    db = (root / "src/social_archive/db.py").read_text(encoding="utf-8")
    sync = (root / "src/social_archive/account_sync.py").read_text(encoding="utf-8")

    finished = re.search(r"completed = status in \{([^}]*)\}", db)
    assert finished, "db.py 里那句「算不算跑完了」不见了——判据要跟着改"
    db_states = set(re.findall(r'"(\w+)"', finished.group(1)))

    gate = re.search(r'if run\["status"\] in \{([^}]*)\}', sync)
    assert gate, "process_job 开头那道闸不见了——判据要跟着改"
    sync_states = set(re.findall(r'"(\w+)"', gate.group(1)))

    assert db_states <= sync_states, (
        f"**db.py 认为已经跑完的状态，process_job 还会接着做**：{sorted(db_states - sync_states)}"
    )
