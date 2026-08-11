"""扩展装载前自检（v0.0.0.7）。

T02 / T04 / T06 / T08 的验收都卡在同一件事：Owner 把扩展载入 Chrome。
那一步只有他能做。**这条判据保证他做那一步时不白做。**

Chrome 加载未打包扩展时，manifest 引用了不存在的文件、或哪个脚本语法错，
会直接拒绝加载，而报错经常只说 "Could not load javascript ..."，
不告诉你是哪一处断了。让 Owner 去猜是浪费他的时间。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "preflight_extension.py"


def test_extension_is_loadable_right_now() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, (
        "扩展现在装不上——Owner 载入时会失败：\n" + completed.stderr
    )
    assert "可以装载" in completed.stdout


def test_preflight_catches_a_missing_file(tmp_path: Path) -> None:
    """判据自己的自检：先证明它抓得到，绿色才有意义。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib

    preflight = importlib.import_module("preflight_extension")
    manifest = ROOT / "apps/browser-extension/manifest.json"
    original = manifest.read_text(encoding="utf-8")
    try:
        import json

        data = json.loads(original)
        data["content_scripts"][0]["js"].append("definitely-not-here.js")
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        found = preflight.problems()
        assert any("definitely-not-here.js" in item for item in found), (
            "自检抓不到 manifest 引用的缺失文件"
        )
    finally:
        manifest.write_text(original, encoding="utf-8")
    # 复原之后必须重新变干净，否则这条判据会污染别的判据
    assert preflight.problems() == []
