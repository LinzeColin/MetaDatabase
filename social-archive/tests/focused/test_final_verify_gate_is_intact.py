"""发布门自己不能是坏的（v0.0.0.7）。

`scripts/final_verify.py` 是 T18 放行前跑的那道结构门。

**它从 T03 起就一直 FAIL，而没有人发现**——因为 T03 删掉了 compose.workers.yaml
（那三个 HTTP worker 被实测证伪），而 final_verify 里还留着一行
`validate_compose.py compose.workers.yaml`。文件不在，门就红，
可这仓的 32 个 CI 工作流没有一个跑 social-archive，于是它红了也没人知道。

这是最坏的一种坏：**用来证明「可以发布」的东西自己是坏的。**

这个文件守两件事：
  1. final_verify 引用的每个脚本都真的存在（删了文件要同步改它）
  2. 本版本新增的三道门确实挂在里面（写了守卫却不挂上门 = 只在手敲 pytest 时生效）
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINAL_VERIFY = ROOT / "scripts" / "final_verify.py"


def _referenced_paths() -> list[str]:
    text = FINAL_VERIFY.read_text(encoding="utf-8")
    block = text.split("def structural_commands", 1)[1].split("def main", 1)[0]
    return re.findall(r'"((?:scripts|compose|src)[^"]*)"', block)


def test_every_path_final_verify_references_exists() -> None:
    paths = _referenced_paths()
    assert len(paths) >= 5, f"只解析出 {len(paths)} 个引用，判据大概没在查"
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, (
        f"final_verify 引用了不存在的文件：{missing}。"
        "发布门会因此永远 FAIL —— 而这仓没有 CI 跑 social-archive，红了也没人知道。"
    )


def test_the_new_v0007_gates_are_wired_into_the_release_gate() -> None:
    """写了守卫却不挂进发布门，等于只在有人手敲 pytest 时才生效。"""
    text = FINAL_VERIFY.read_text(encoding="utf-8")
    for script in ("scripts/preflight_extension.py",
                   "scripts/scan_plaintext_credentials.py",
                   "scripts/validate_deployment_contract.py"):
        assert script in text, f"{script} 没有挂进 final_verify"


def test_the_deleted_workers_compose_is_not_referenced_anymore() -> None:
    text = FINAL_VERIFY.read_text(encoding="utf-8")
    block = text.split("def structural_commands", 1)[1].split("def main", 1)[0]
    code = "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))
    assert "compose.workers.yaml" not in code, (
        "compose.workers.yaml 已随 T03 删除，final_verify 不该再校验它"
    )


def test_release_gate_actually_passes_right_now() -> None:
    """最直接的一条：现在就跑一遍，它必须绿。

    这条比上面三条都强——上面查的是「引用对不对」，这条查的是「它真的过不过」。
    """
    completed = subprocess.run(
        [sys.executable, str(FINAL_VERIFY)], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, (
        "发布门当前是 FAIL —— 详见 evidence/final-verification.json：\n"
        + completed.stdout[-500:] + completed.stderr[-500:]
    )
    assert "PASS" in completed.stdout
