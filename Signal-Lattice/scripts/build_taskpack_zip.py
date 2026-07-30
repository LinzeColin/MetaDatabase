#!/usr/bin/env python3
"""Build a deterministic v0.0.0.1.39 development taskpack, not a formal release ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.receipts import canonical_json_bytes, load_self_hashed, sha256_file


EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".whl")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def include(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.is_symlink():
        raise ValueError("SYMLINK_FORBIDDEN:" + rel.as_posix())
    if any(part in EXCLUDED_PARTS or part.endswith((".egg-info", ".dist-info")) for part in rel.parts):
        return False
    if rel.as_posix() == "FINAL_PACKAGE_MANIFEST.json" or rel.as_posix().endswith(EXCLUDED_SUFFIXES):
        return False
    return path.is_file()


def source_rows(root: Path) -> list[tuple[str, bytes, int]]:
    rows: list[tuple[str, bytes, int]] = []
    for path in sorted(root.rglob("*")):
        if not include(path, root):
            continue
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        rows.append(("Signal-Lattice/" + path.relative_to(root).as_posix(), path.read_bytes(), mode))
    return rows


def wrapper_files(root: Path, seal: dict[str, object]) -> list[tuple[str, bytes, int]]:
    introduction = f"""# Signal Lattice v{VERSION}｜重新封存最终开发任务包

这是 Owner 已批准交付给 Build Agent 的 **SEALED_TASKPACK**，仅用于目标仓兼容、真实凭证绑定、OVH 部署、即时故障注入、备份恢复回滚与 Status 收尾；不代表正式生产发布 PASS。

## 唯一入口

1. 阅读本文件、`CODEX_LAST_MILE_PROMPT.txt`、`PURSUING_GOAL.txt` 和 `ROADMAP.md`；
2. 进入 `Signal-Lattice/`，再按其中 `00_READ_FIRST.md` 的唯一顺序执行；
3. `Signal-Lattice/evidence/owner_gate/taskpack_seal.json` 是机器封存收据；其 `taskpack_sha256` 是冻结内容身份哈希，不是 ZIP 字节哈希；本 ZIP 的实际 SHA-256 见同目录的 `.zip.sha256` 文件；
4. 股票 Skill 的唯一 Git 路径是 `Signal-Lattice/Stock_Skill/`。本任务包携带该源码树，`embedded_stock_skill_payload_sha256` 将其与封存收据绑定。

## 强制安全模式

- 运行期 Agent 依赖：0
- 运行期模型 API 与 LLM Token：0
- 自动交易：关闭
- 上游 Skill 写回：关闭
- macOS / launchd / 用户本机常驻：禁止
- 正式来源、市场数据与发布验收未完成前：`RESEARCH_AND_NO_ACTION`

封存内容身份：`{seal["taskpack_sha256"]}`
股票 Skill 源码身份：`{seal["embedded_stock_skill_payload_sha256"]}`
"""
    return [
        ("00_READ_FIRST.md", introduction.encode("utf-8"), 0o644),
        ("CODEX_LAST_MILE_PROMPT.txt", (root / "CODEX_LAST_MILE_PROMPT.txt").read_bytes(), 0o644),
        ("PURSUING_GOAL.txt", (root / "PURSUING_GOAL.txt").read_bytes(), 0o644),
        ("ROADMAP.md", (root / "ROADMAP.md").read_bytes(), 0o644),
    ]


def final_manifest(rows: list[tuple[str, bytes, int]], seal_path: Path, seal: dict[str, object]) -> dict[str, object]:
    files = [
        {"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "mode": oct(mode)}
        for name, content, mode in rows
    ]
    return {
        "schema_version": "1.0.0",
        "version": VERSION,
        "scope": "SEALED_DEVELOPMENT_TASKPACK_ONLY",
        "taskpack_identity_sha256": seal["taskpack_sha256"],
        "taskpack_seal_file_sha256": sha256_file(seal_path),
        "embedded_stock_skill_payload_sha256": seal["embedded_stock_skill_payload_sha256"],
        "file_count": len(files),
        "payload_bytes": sum(item["size"] for item in files),
        "payload_sha256": hashlib.sha256(canonical_json_bytes(files)).hexdigest(),
        "files": files,
    }


def verify_archive(path: Path, prefix: str, manifest: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory(prefix="signal-lattice-taskpack-verify-") as temp:
        extracted = Path(temp)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or any(name.startswith("/") or ".." in Path(name).parts for name in names):
                raise SystemExit("ZIP_PATH_SET_INVALID")
            archive.extractall(extracted)
        package_root = extracted / prefix.rstrip("/")
        actual = json.loads((package_root / "FINAL_PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
        if actual != manifest:
            raise SystemExit("FINAL_MANIFEST_MISMATCH")
        for row in manifest["files"]:
            file_path = package_root / row["path"]
            if not file_path.is_file() or file_path.stat().st_size != row["size"] or sha256_file(file_path) != row["sha256"]:
                raise SystemExit("ZIP_FILE_MISMATCH:" + row["path"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if root == output.parent or root in output.parents:
        raise SystemExit("OUTPUT_MUST_BE_OUTSIDE_CANDIDATE_ROOT")
    receipt_path = output.with_name(output.name + ".sha256")
    if output.exists() or receipt_path.exists():
        raise SystemExit("OUTPUT_OR_RECEIPT_ALREADY_EXISTS")
    verification = subprocess.run(
        [sys.executable, "scripts/verify_taskpack_seal.py", "--root", str(root)],
        cwd=root, capture_output=True, text=True, timeout=300,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(root / "src"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if verification.returncode != 0:
        raise SystemExit("TASKPACK_SEAL_NOT_PASS:" + (verification.stdout + verification.stderr)[-500:])
    package = subprocess.run(
        [sys.executable, "scripts/verify_package.py", "--root", str(root), "--manifest", str(root / "MANIFEST.json")],
        cwd=root, capture_output=True, text=True, timeout=300,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(root / "src"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if package.returncode != 0:
        raise SystemExit("PACKAGE_GUARD_NOT_PASS:" + (package.stdout + package.stderr)[-500:])
    seal_path = root / "evidence/owner_gate/taskpack_seal.json"
    seal = load_self_hashed(seal_path)
    rows = wrapper_files(root, seal) + source_rows(root)
    if len({name for name, _, _ in rows}) != len(rows):
        raise SystemExit("DUPLICATE_TASKPACK_PATH")
    manifest = final_manifest(rows, seal_path, seal)
    prefix = f"Signal_Lattice_v{VERSION}/"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="signal-lattice-taskpack-") as temp:
        temporary_zip = Path(temp) / output.name
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, content, mode in rows:
                info = zipfile.ZipInfo(prefix + name, FIXED_TIME)
                info.create_system = 3
                info.external_attr = (mode & 0xFFFF) << 16
                archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            info = zipfile.ZipInfo(prefix + "FINAL_PACKAGE_MANIFEST.json", FIXED_TIME)
            info.create_system = 3
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        verify_archive(temporary_zip, prefix, manifest)
        shutil.copy2(temporary_zip, output)
    zip_sha256 = sha256_file(output)
    receipt_path.write_text(f"{zip_sha256}  {output.name}\n", encoding="utf-8")
    print(json.dumps({
        "state": "PASS", "scope": "SEALED_DEVELOPMENT_TASKPACK_ONLY", "output": output.as_posix(),
        "zip_sha256": zip_sha256, "receipt": receipt_path.as_posix(), "file_count": len(rows) + 1,
        "taskpack_identity_sha256": seal["taskpack_sha256"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
