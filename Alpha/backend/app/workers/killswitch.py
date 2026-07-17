"""杀开关(文件载体):控制页/邮件指令/Supervisor 都能拍下;网关每单前必查。

文件存在 = 已触发。内容记录原因与时间(审计),清除 = 恢复。
选择文件而非库表:数据库故障时杀开关必须仍然可用(失败关闭的最后一道)。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class KillSwitch:
    def __init__(self, path: str | Path = "runtime/KILL_SWITCH") -> None:
        self._path = Path(path)

    def engage(self, *, reason: str, source: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"reason": reason, "source": source,
                 "engaged_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
            )
        )

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def active(self) -> bool:
        return self._path.exists()

    def detail(self) -> Optional[dict]:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"reason": "杀开关文件不可读(视同已触发)", "source": "unknown"}
