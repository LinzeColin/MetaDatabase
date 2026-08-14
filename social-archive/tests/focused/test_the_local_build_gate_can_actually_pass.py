r"""本机构建那条路的磁盘门，必须真的能放行（2026-08-10）。

## 它守的是一次「恒中止」

本机构建这条路存在的**全部理由**就是绕开那道「主机至少 5G」的门
（主机 38G 盘 97% 满，大头是别的项目的镜像，我不动；我自己占的清干净也到不了 5G）。
我给它写了一道按实际镜像大小算的门，并加了一句「人为设了更高的门槛就取高的那个」：

    if (( MIN_FREE_KB > DERIVED_KB )); then …   # 保留人为门槛

**而 `MIN_FREE_GB` 默认就是 5。** 于是「取高的那个」永远取到 5G，
按镜像算出来的 0.82G 一次都用不上——这条路从第一次跑起就是恒中止的：

    镜像 0.11G，主机可用 1.35G，门槛 5.00G（镜像×3 + 512M 余量）
    部署中止：主机放不下这个镜像（可用 1.35G < 门槛 5.00G）。

「阈值高过天花板 → 恒红」，这个仓记过一次，我又造了一个。

## 判据怎么打

**不查字符串**——把脚本里那段门的代码原样抠出来，喂进 bash 真跑，
用三组数看它的判断：

  1. 默认（没设环境变量）+ 盘够放这个镜像 → **放行**（这是恒中止那次的那组数）
  2. 显式设了 5G 门槛（演练就是这么把「磁盘不够」那条路走一遍的）→ 中止
  3. 盘真的放不下 → 中止
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"

# 那次恒中止的真实数字：tar 0.11G，主机可用 1.35G
REAL_TAR_KB = 115_000
REAL_FREE_KB = 1_415_577


def _gate_snippet() -> str:
    text = DEPLOY.read_text(encoding="utf-8")
    start = text.index("  DERIVED_KB=$((")
    end = text.index("  printf '  送过去并 load", start)
    snippet = text[start:end]
    assert "MIN_FREE_KB" in snippet and "fail " in snippet, snippet[:200]
    return snippet


def _run(tar_kb: int, free_kb: int, explicit_gb: str | None) -> subprocess.CompletedProcess[str]:
    script = f"""
set -u
show_gb() {{ awk -v kb="$1" 'BEGIN{{printf "%.2f", kb/1048576}}'; }}
fail() {{ echo "ABORT: $*"; exit 9; }}
IMAGE_TAR=/dev/null
TAR_KB={tar_kb}
FREE_KB={free_kb}
MIN_FREE_GB="${{SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB:-5}}"
MIN_FREE_KB=$(( MIN_FREE_GB * 1048576 ))
{_gate_snippet()}
echo "PASSED-THE-GATE"
"""
    env = dict(os.environ)
    env.pop("SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB", None)
    if explicit_gb is not None:
        env["SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB"] = explicit_gb
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=env, check=False)


def test_the_snippet_was_really_extracted() -> None:
    """反空扫：抠出来的要是空的，下面每条都会白过。"""
    snippet = _gate_snippet()
    assert snippet.count("\n") >= 8, snippet
    assert "DERIVED_KB" in snippet and "TAR_KB" in snippet


def test_the_real_numbers_that_aborted_now_pass() -> None:
    """**这组数就是恒中止那次的**：镜像 0.11G、可用 1.35G、没设环境变量。"""
    done = _run(REAL_TAR_KB, REAL_FREE_KB, None)
    assert "PASSED-THE-GATE" in done.stdout, (
        "本机构建的磁盘门又把自己堵死了——它存在的理由就是绕开那个 5G 默认值。\n"
        + done.stdout + done.stderr)


def test_a_drill_can_still_force_it_red() -> None:
    """演练靠显式抬门槛把「磁盘不够 → 中止」那条路真走一遍——那个能力不能丢。"""
    done = _run(REAL_TAR_KB, REAL_FREE_KB, "5")
    assert done.returncode == 9 and "ABORT" in done.stdout, done.stdout + done.stderr


def test_a_disk_that_really_cannot_hold_it_aborts() -> None:
    """门还得真的会拦：盘只剩 0.2G，放不下一个 0.11G 的镜像（×3 + 余量）。"""
    done = _run(REAL_TAR_KB, 200_000, None)
    assert done.returncode == 9 and "ABORT" in done.stdout, done.stdout + done.stderr


@pytest.mark.parametrize("tar_gb,free_gb,expect_pass", [
    (0.11, 1.35, True),    # 恒中止那次
    (0.11, 0.50, False),   # 刚好不够（0.11×3+0.5 = 0.83）
    (1.00, 4.00, True),    # 大镜像、盘也大
    (1.00, 3.00, False),   # 大镜像、盘不够（1×3+0.5 = 3.5）
])
def test_the_gate_scales_with_the_image(tar_gb: float, free_gb: float, expect_pass: bool) -> None:
    done = _run(int(tar_gb * 1048576), int(free_gb * 1048576), None)
    passed = "PASSED-THE-GATE" in done.stdout
    assert passed is expect_pass, (
        f"镜像 {tar_gb}G / 可用 {free_gb}G：期望{'放行' if expect_pass else '中止'}，"
        f"实际{'放行' if passed else '中止'}\n" + done.stdout + done.stderr)
