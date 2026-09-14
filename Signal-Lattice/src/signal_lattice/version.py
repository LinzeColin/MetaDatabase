"""从唯一发布元数据解析运行时版本。"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path
import re


_PYPROJECT_VERSION = re.compile(
    r'^version\s*=\s*["\']([^"\']+)["\']\s*$', re.MULTILINE
)


def _source_tree_version() -> str:
    """使源码树测试与已安装 wheel 使用同一份发布元数据。"""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    matched = _PYPROJECT_VERSION.search(pyproject.read_text(encoding="utf-8"))
    if matched is None:
        raise RuntimeError("PYPROJECT_VERSION_UNAVAILABLE")
    return matched.group(1)


_SOURCE_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
if _SOURCE_PYPROJECT.is_file():
    VERSION = _source_tree_version()
else:
    try:
        VERSION = installed_version("signal-lattice")
    except PackageNotFoundError as exc:
        raise RuntimeError("PACKAGE_VERSION_UNAVAILABLE") from exc
