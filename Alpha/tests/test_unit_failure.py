"""定时任务失败自告警:同一单元连续失败只发一封,--ok 恢复,下次失败再发。"""

from sqlalchemy import select

import scripts.notify_unit_failure as nuf
from backend.app.domain.models import OutboxEvent
from backend.app.store.db import create_session_factory, init_engine


def test_repeated_unit_failure_one_mail_and_ok_resolves(shadow_env):
    factory = create_session_factory(init_engine())

    def kinds():
        with factory() as s:
            return [r.event_type for r in s.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at))]

    unit = "alpha-equity-snapshot.service"
    for _ in range(5):
        assert nuf.main([unit]) == 0
    assert kinds() == ["UNIT_FAILED"]
    nuf.main(["--ok", unit])
    assert kinds() == ["UNIT_FAILED", "ALERT_RECOVERED"]
    nuf.main(["--ok", unit])                                # 已恢复后再成功不再发
    assert len(kinds()) == 2
    nuf.main([unit])                                        # 下次失败再发
    assert kinds()[-1] == "UNIT_FAILED" and len(kinds()) == 3
    assert nuf.UNIT_CN["alpha-equity-snapshot.service"] == "净值快照"
