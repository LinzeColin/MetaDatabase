#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.receipts import canonical_json_bytes, load_self_hashed, sha256_file

EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".zip", ".whl")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def include(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.is_symlink():
        raise ValueError("SYMLINK_FORBIDDEN:" + rel.as_posix())
    if any(part in EXCLUDED_PARTS or part.endswith((".egg-info", ".dist-info")) for part in rel.parts):
        return False
    if rel.as_posix() in {"FINAL_PACKAGE_MANIFEST.json"} or rel.as_posix().endswith(EXCLUDED_SUFFIXES):
        return False
    return path.is_file()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if root == output.parent or root in output.parents:
        raise SystemExit("OUTPUT_MUST_BE_OUTSIDE_CANDIDATE_ROOT")
    approval = load_self_hashed(args.approval)
    subject = json.loads((root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
    if approval.get("approved") is not True:
        raise SystemExit("OWNER_APPROVAL_REQUIRED")
    if approval.get("version") != VERSION or subject.get("version") != VERSION:
        raise SystemExit("VERSION_MISMATCH")
    if subject.get("state") != "FROZEN" or approval.get("subject_sha256") != subject.get("subject_sha256"):
        raise SystemExit("SUBJECT_APPROVAL_MISMATCH")
    canonical = json.loads((root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))
    if canonical.get("current_phase") != "OWNER_GATE" or canonical.get("owner_gate", {}).get("eligible") is not True:
        raise SystemExit("OWNER_GATE_NOT_READY")
    pass_c = load_self_hashed(root / "evidence/skill_router/pass_c.json")
    if pass_c.get("state") != "PASS" or pass_c.get("formal_pass_claimed") is not True or pass_c.get("subject_sha256") != subject.get("subject_sha256"):
        raise SystemExit("SKILL_PASS_C_NOT_PASS")
    gate = subprocess.run(
        [sys.executable, "scripts/verify_formal_gate.py", "--root", str(root)],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(root / "src"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
    )
    if gate.returncode != 0:
        raise SystemExit("FORMAL_GATE_NOT_PASS:" + gate.stdout[-500:])
    package = subprocess.run(
        [sys.executable, "scripts/verify_package.py", "--root", str(root), "--manifest", str(root / "MANIFEST.json")],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(root / "src"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
    )
    if package.returncode != 0:
        raise SystemExit("PACKAGE_GUARD_NOT_PASS:" + package.stdout[-500:])
    files = [path for path in sorted(root.rglob("*")) if include(path, root)]
    rows = [{"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": sha256_file(path)} for path in files]
    manifest = {
        "schema_version": "1.0.0",
        "version": VERSION,
        "subject_sha256": subject["subject_sha256"],
        "payload_file_count": len(rows),
        "payload_bytes": sum(row["size"] for row in rows),
        "files": rows,
    }
    manifest["payload_sha256"] = hashlib.sha256(canonical_json_bytes(rows)).hexdigest()
    prefix = f"Signal_Lattice_v{VERSION}/"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_zip = Path(tmpdir) / output.name
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, row in zip(files, rows, strict=True):
                info = zipfile.ZipInfo(prefix + row["path"], FIXED_TIME)
                info.create_system = 3
                mode = 0o755 if os.access(path, os.X_OK) else 0o644
                info.external_attr = (mode & 0xFFFF) << 16
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            info = zipfile.ZipInfo(prefix + "FINAL_PACKAGE_MANIFEST.json", FIXED_TIME)
            info.create_system = 3
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with tempfile.TemporaryDirectory() as extract_dir:
            extract = Path(extract_dir)
            with zipfile.ZipFile(temp_zip) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)) or any(name.startswith("/") or ".." in Path(name).parts for name in names):
                    raise SystemExit("ZIP_PATH_SET_INVALID")
                archive.extractall(extract)
            extracted_root = extract / prefix.rstrip("/")
            extracted_manifest = json.loads((extracted_root / "FINAL_PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
            if extracted_manifest != manifest:
                raise SystemExit("FINAL_MANIFEST_MISMATCH")
            for row in rows:
                path = extracted_root / row["path"]
                if not path.is_file() or path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
                    raise SystemExit("ZIP_FILE_MISMATCH:" + row["path"])
        shutil.copy2(temp_zip, output)
    result = {"state": "PASS", "output": output.as_posix(), "zip_sha256": sha256_file(output), "file_count": len(rows) + 1, "subject_sha256": subject["subject_sha256"]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
