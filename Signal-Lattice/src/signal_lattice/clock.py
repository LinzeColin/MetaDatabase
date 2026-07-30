from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

class Clock(Protocol):
    def now(self) -> datetime: ...

class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

@dataclass(frozen=True)
class FakeClock:
    value: datetime
    def now(self) -> datetime:
        if self.value.tzinfo is None:
            return self.value.replace(tzinfo=timezone.utc)
        return self.value.astimezone(timezone.utc)
