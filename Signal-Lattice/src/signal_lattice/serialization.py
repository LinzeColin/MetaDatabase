"""运行期报告的严格 JSON 边界。"""

from __future__ import annotations

import json
from typing import Any


class JsonSerializationConstraintError(ValueError):
    """报告包含 JSON 标准不接受的数值时触发。"""


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """拒绝 NaN 与 Infinity，避免把浏览器无法解析的报告写出。"""
    try:
        return json.dumps(value, allow_nan=False, **kwargs)
    except ValueError as exc:
        raise JsonSerializationConstraintError("NONFINITE_JSON_VALUE") from exc
