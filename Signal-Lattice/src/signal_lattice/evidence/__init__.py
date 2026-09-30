"""时点正确的 SEC 事实库与免 key 采集（标准库实现，零依赖）。"""

from .collector import collect_company
from .factstore import Fact, FactStore
from .sec_client import (
    DEFAULT_USER_AGENT,
    GLOBAL_LIMITER,
    MAX_ATTEMPTS,
    MAX_REQUESTS_PER_SECOND,
    RateLimiter,
    SecClient,
    SecFetchError,
    SecNotFound,
    form4_raw_xml_name,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "GLOBAL_LIMITER",
    "MAX_ATTEMPTS",
    "MAX_REQUESTS_PER_SECOND",
    "Fact",
    "FactStore",
    "RateLimiter",
    "SecClient",
    "SecFetchError",
    "SecNotFound",
    "collect_company",
    "form4_raw_xml_name",
]
