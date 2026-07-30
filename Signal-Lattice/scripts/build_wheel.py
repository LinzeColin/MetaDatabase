#!/usr/bin/env python3
"""Create a reproducible pure-Python wheel using only the standard library."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path


FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_hash(content: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")


def wheel_name(project: dict[str, object]) -> str:
    distribution = str(project["name"]).replace("-", "_")
    return f"{distribution}-{project['version']}-py3-none-any.whl"


def wheel_files(root: Path) -> tuple[str, list[tuple[str, bytes]]]:
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    distribution = str(metadata["name"]).replace("-", "_")
    version = str(metadata["version"])
    dist_info = f"{distribution}-{version}.dist-info"
    files: list[tuple[str, bytes]] = []
    package_root = root / "src" / "signal_lattice"
    for path in sorted(package_root.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".sql"}:
            files.append((path.relative_to(root / "src").as_posix(), path.read_bytes()))
    if not files:
        raise SystemExit("WHEEL_PACKAGE_SOURCE_MISSING")
    files.extend([
        (f"{dist_info}/METADATA", (
            "Metadata-Version: 2.1\n"
            f"Name: {metadata['name']}\n"
            f"Version: {version}\n"
            f"Summary: {metadata.get('description', '')}\n"
            f"Requires-Python: {metadata['requires-python']}\n"
        ).encode("utf-8")),
        (f"{dist_info}/WHEEL", b"Wheel-Version: 1.0\nGenerator: signal-lattice-stdlib\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
        (f"{dist_info}/entry_points.txt", b"[console_scripts]\nsignal-lattice = signal_lattice.cli:main\n"),
    ])
    record_lines = [f"{name},{record_hash(content)},{len(content)}" for name, content in files]
    record_path = f"{dist_info}/RECORD"
    files.append((record_path, ("\n".join(record_lines) + f"\n{record_path},,\n").encode("utf-8")))
    return wheel_name(metadata), files


def write_wheel(root: Path, output_dir: Path) -> Path:
    filename, files = wheel_files(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / filename
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in files:
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.create_system = 3
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    with tempfile.TemporaryDirectory(prefix="signal-lattice-wheel-") as temp:
        first_dir = Path(temp) / "first"
        second_dir = Path(temp) / "second"
        first = write_wheel(root, first_dir)
        second = write_wheel(root, second_dir)
        if first.read_bytes() != second.read_bytes():
            raise SystemExit("NON_REPRODUCIBLE_WHEEL")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / first.name
        shutil.copy2(first, destination)
    receipt = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "wheel": destination.name,
        "sha256": digest(destination),
        "size": destination.stat().st_size,
        "build_count": 2,
        "byte_identical": True,
        "network_required": False,
        "build_backend": "STDLIB_PEP427",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
