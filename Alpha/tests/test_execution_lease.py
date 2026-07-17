"""ALPHA-LIVE-035:执行租约互斥与接管。"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.execution.lease import LeaseManager, LeaseUnavailableError
from backend.app.store.db import create_session_factory, init_engine

NOW = datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc)


def factory(tmp_path):
    return create_session_factory(init_engine(f"sqlite:///{tmp_path / 'lease.sqlite'}"))


def test_mutual_exclusion_while_valid(tmp_path):
    f = factory(tmp_path)
    a = LeaseManager(f, holder_id="A", now_fn=lambda: NOW)
    b = LeaseManager(f, holder_id="B", now_fn=lambda: NOW + timedelta(seconds=5))
    a.acquire()
    with pytest.raises(LeaseUnavailableError):
        b.acquire()                      # A 仍有效:B 拿不到
    assert a.held() and not b.held()
    assert a.current_holder() == "A"


def test_takeover_after_expiry(tmp_path):
    f = factory(tmp_path)
    a = LeaseManager(f, holder_id="A", ttl_seconds=30, now_fn=lambda: NOW)
    a.acquire()
    b = LeaseManager(f, holder_id="B", now_fn=lambda: NOW + timedelta(seconds=31))
    b.acquire()                          # A 过期:B 接管
    assert b.current_holder() == "B"
    assert a.held() is False             # A 的视角:已丢失


def test_renew_extends_and_fails_after_takeover(tmp_path):
    f = factory(tmp_path)
    clock = {"t": NOW}
    a = LeaseManager(f, holder_id="A", ttl_seconds=30, now_fn=lambda: clock["t"])
    a.acquire()
    clock["t"] = NOW + timedelta(seconds=20)
    a.renew()                            # 未过期可续
    assert a.held()
    clock["t"] = NOW + timedelta(seconds=80)
    with pytest.raises(LeaseUnavailableError):
        a.renew()                        # 过期后不可续(可能已被接管)


def test_release_frees_lease(tmp_path):
    f = factory(tmp_path)
    a = LeaseManager(f, holder_id="A", now_fn=lambda: NOW)
    a.acquire()
    a.release()
    b = LeaseManager(f, holder_id="B", now_fn=lambda: NOW + timedelta(seconds=1))
    b.acquire()
    assert b.current_holder() == "B"


def test_same_holder_reacquire_is_idempotent(tmp_path):
    f = factory(tmp_path)
    a = LeaseManager(f, holder_id="A", now_fn=lambda: NOW)
    a.acquire()
    a.acquire()                          # 同持有者重复取得 = 刷新
    assert a.held()
