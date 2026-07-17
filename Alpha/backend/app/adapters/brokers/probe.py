"""辖区能力探针(ALPHA-LIVE-020,契约第 4.5 条)。

接口实测证据 -> 判定 -> JurisdictionCapability 落库。
三项全绿(账户状态正常 + 美股交易权限 + 美股行情权限)才 ALLOW;任何缺失即 DENY。
DENY 即禁买(AGENTS.md 第 4 节:不做任何规避;探针不过即禁买)。
"""

from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters.brokers.base import ProbeEvidence
from backend.app.domain.models import JurisdictionCapability

#: 判定口径(美股首发;港股第二阶段另行登记新探针口径)
ACTIVE_ACCOUNT_STATUSES = frozenset({"ACTIVE", "NORMAL"})
REQUIRED_TRD_PERMISSION = "US_STOCK"
REQUIRED_QUOTE_MARKET = "US"


def evaluate(evidence: ProbeEvidence) -> dict:
    account_ok = evidence.account_status.upper() in ACTIVE_ACCOUNT_STATUSES
    trd_ok = REQUIRED_TRD_PERMISSION in {p.upper() for p in evidence.trd_permissions}
    quote_ok = any(
        q.market.upper() == REQUIRED_QUOTE_MARKET and q.ok for q in evidence.quote_permissions
    )
    verdict = "ALLOW" if (account_ok and trd_ok and quote_ok) else "DENY"
    return {
        "account_ok": account_ok,
        "trd_ok": trd_ok,
        "quote_ok": quote_ok,
        "verdict": verdict,
    }


def run_probe_and_persist(
    evidence: ProbeEvidence,
    session_factory: sessionmaker[Session],
    *,
    account_principal: str,
    location: str,
) -> dict:
    """判定并落库。返回判定结果(含 capability_id)。"""
    result = evaluate(evidence)
    with session_factory() as session, session.begin():
        row = JurisdictionCapability(
            account_principal=account_principal,
            location=location,
            api_available=True,  # 能拿到证据即接口可用;拿不到证据的路径根本走不到这里
            buy_permission=(result["verdict"] == "ALLOW"),
            evidence_source=json.dumps(
                {
                    "account_status": evidence.account_status,
                    "trd_permissions": evidence.trd_permissions,
                    "quote_permissions": [asdict(q) for q in evidence.quote_permissions],
                    "probed_at": evidence.probed_at.isoformat() if evidence.probed_at else None,
                    "checks": {k: v for k, v in result.items() if k != "verdict"},
                },
                ensure_ascii=False,
            ),
            verdict=result["verdict"],
            probed_at=evidence.probed_at,
        )
        session.add(row)
        session.flush()
        result["capability_id"] = row.capability_id
    return result
