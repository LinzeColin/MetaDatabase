"""守住「这次部署要不要重建镜像」这个判断（2026-08-07）。

这道判断会让部署**跳过构建**。所以它说错一次的代价是不对称的：
说「要重建」而其实不用 → 白花几分钟；
说「不用重建」而其实要 → 他打开界面，改的东西没上去，而部署报了成功。

**所以这里的判据主要在证明它不会说错第二种。**

不连任何机器：喂两个字典给 `decide()`，喂真 Dockerfile 给解析函数。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/does_this_deploy_need_a_rebuild.py"

_spec = importlib.util.spec_from_file_location("_rebuild_decision", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_rebuild_decision"] = _module
_spec.loader.exec_module(_module)

decide = _module.decide
image_inputs_from_dockerfile = _module.image_inputs_from_dockerfile


def _needs_rebuild(buckets: dict) -> bool:
    return bool(buckets["runtime_differs"] or buckets["missing_from_image"])


# ---------------------------------------------------------------- 会不会漏

def test_a_changed_runtime_file_forces_a_rebuild() -> None:
    """**反例**：服务真跑的文件不一样了，必须说「要重建」。"""
    buckets = decide({"src/social_archive/api.py": "aaa"},
                     {"src/social_archive/api.py": "bbb"})
    assert _needs_rebuild(buckets)
    assert buckets["runtime_differs"] == ["src/social_archive/api.py"]


def test_a_file_missing_from_the_image_forces_a_rebuild() -> None:
    """**新加的文件根本不在镜像里**，也是「要重建」。

    只比「两边都有的那些」是这类判断最常见的漏法——新文件永远不在交集里，
    于是「全都一样」和「少了一个」得到同一个结论。
    """
    buckets = decide({"apps/pwa/新页面.js": "aaa"}, {})
    assert _needs_rebuild(buckets)
    assert buckets["missing_from_image"] == ["apps/pwa/新页面.js"]


def test_non_code_files_are_compared_too() -> None:
    """**不按后缀过滤。** 图标、.md、.txt 改了同样要重建。

    漂移检查那道门按后缀过滤（.py/.sh/.js/.css/.html/.json）——对一道报警的门
    是小缺口，对一个「可以不构建」的决定是真窟窿。
    """
    for name in ("apps/pwa/icon.svg", "README.md", "VERSION",
                 "apps/browser-extension/icon-128.png"):
        assert _needs_rebuild(decide({name: "aaa"}, {name: "bbb"})), \
            f"{name} 改了却说不用重建"


def test_dependency_and_version_files_are_in_scope() -> None:
    """pyproject.toml / VERSION 改了要重建——`pip install .` 是在镜像里跑的。"""
    assert _needs_rebuild(decide({"pyproject.toml": "a"}, {"pyproject.toml": "b"}))


# ------------------------------------------------------- 会不会白构建（正例）

def test_identical_inputs_skip_the_build() -> None:
    """**正例必须是绿的。** 全都一样时要真的说「不用重建」。

    只验反例是红的不够：一道永远说「要重建」的判断也能让上面每一条通过，
    而它等于没做。
    """
    same = {"src/social_archive/api.py": "aaa", "apps/pwa/app.js": "bbb"}
    assert not _needs_rebuild(decide(same, dict(same)))


def test_only_dev_scripts_differing_skips_the_build() -> None:
    """判据和演练进了镜像但容器从来不跑——它们不同不构成重建理由。"""
    buckets = decide(
        {"scripts/check_brand.py": "aaa", "scripts/pwa_render_drill.py": "ccc",
         "src/social_archive/api.py": "same"},
        {"scripts/check_brand.py": "bbb", "src/social_archive/api.py": "same"})
    assert not _needs_rebuild(buckets)
    assert sorted(buckets["dev_only_differs"]) == [
        "scripts/check_brand.py", "scripts/pwa_render_drill.py"]


def test_the_exemption_uses_the_same_rule_as_the_drift_check() -> None:
    """**这条规则只有一份。** 抄成两份的那天，一边说「不用重建」，
    另一边说「服务在跑旧代码」，而两边都自称查过了。
    """
    source_file = Path(_module.container_never_runs.__code__.co_filename)
    assert source_file.name == "check_production_matches_the_repo.py", (
        f"重建判断用的规则来自 {source_file.name}，不是漂移检查那一份")
    assert "def container_never_runs" not in SCRIPT.read_text(encoding="utf-8"), (
        "重建判断里自己又定义了一份 container_never_runs——**这就是抄第二份**")


# ------------------------------------------------- 镜像输入清单是现读的，不是抄的

def test_image_inputs_are_read_from_the_real_dockerfile() -> None:
    """**对着真 Dockerfile 跑，不用夹具。**

    夹具是我自己编的，永远和我脑子里那份一致；只有真文件能证伪我。
    """
    sources, error = image_inputs_from_dockerfile(ROOT / "Dockerfile")
    assert error is None, error
    copied = [line.split()[1:-1] for line in
              (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
              if line.strip().upper().startswith("COPY ")]
    expected = [token for tokens in copied for token in tokens]
    assert sources == expected, (
        f"COPY 清单没读全：Dockerfile 里是 {expected}，读出来是 {sources}")
    for must in ("src", "apps", "scripts", "pyproject.toml", "VERSION"):
        assert must in sources, f"{must} 进了镜像却不在比对范围里"


def test_a_new_copy_line_is_picked_up(tmp_path: Path) -> None:
    """**加一条 COPY，它必须跟着覆盖。**

    这是抄常量和现读的区别所在：抄一份的话，新加的 `COPY deploy ./deploy`
    会被安静地漏掉，然后这道判断说「不用重建」——它最不该说错的一句话。
    """
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\nCOPY src ./src\nCOPY deploy ./deploy\n",
                          encoding="utf-8")
    sources, error = image_inputs_from_dockerfile(dockerfile)
    assert error is None and sources == ["src", "deploy"]


def test_unreadable_copy_forms_are_refused_not_guessed(tmp_path: Path) -> None:
    """看不懂的 COPY 要**说看不懂**，由调用方按「要重建」处理。

    猜错的方向是致命的那一侧：把没覆盖到的东西当成「一样」。
    """
    for line, why in (
        ("COPY --from=builder /out ./out", "多阶段"),
        ("COPY apps/*.js ./apps/", "通配符"),
        ("COPY src ./lib", "改了名"),
        ("COPY src", "只有一个词"),
    ):
        dockerfile = tmp_path / f"Dockerfile.{why}"
        dockerfile.write_text(f"FROM python:3.12-slim\n{line}\n", encoding="utf-8")
        sources, error = image_inputs_from_dockerfile(dockerfile)
        assert error, f"{line}（{why}）应该被判为读不懂，实际读成了 {sources}"


def test_a_dockerfile_with_no_copy_is_an_error_not_an_empty_answer(tmp_path: Path) -> None:
    """**一条 COPY 都没读到 ≠ 没有输入。** 空默认值被读成「没问题」是这个仓的老病。"""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\nRUN echo hi\n", encoding="utf-8")
    sources, error = image_inputs_from_dockerfile(dockerfile)
    assert error and not sources


# ------------------------------------------------------------ 构建产物不算差异

def test_build_artifacts_only_in_the_image_are_not_differences() -> None:
    """镜像里多出来的（pip 装的 .egg-info、dist/ 里的扩展包）不算「不一致」。

    方向只看「仓 → 镜像」。反过来算的话，每一次都会说要重建，等于没做。
    """
    buckets = decide({"src/social_archive/api.py": "same"},
                     {"src/social_archive/api.py": "same",
                      "src/social_archive.egg-info/PKG-INFO": "生成的"})
    assert not _needs_rebuild(buckets)


def test_pycache_is_skipped_on_both_sides() -> None:
    skip = _module._skip
    assert skip("src/social_archive/__pycache__/api.cpython-312.pyc")
    assert skip("src/social_archive.egg-info/PKG-INFO")
    assert not skip("src/social_archive/api.py")
    assert not skip("apps/pwa/app.js")
