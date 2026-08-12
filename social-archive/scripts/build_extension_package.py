#!/usr/bin/env python3
"""Build a deterministic, secret-free Chrome extension ZIP."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "browser-extension"
OUTPUT = ROOT / "dist" / "social-archive-extension.zip"
EXCLUDED = {".DS_Store"}


def main() -> int:
    # 版本只有一个真源：仓根的 VERSION 文件。
    #
    # 这里原先写死 "0.0.0.6"。写死的后果不是打包失败——是**版本号只能靠人记得
    # 同时改两处**，而其中一处改漏了就会在打包这一步才炸，且报错说的是
    # 「manifest 版本必须是 0.0.0.6」，听起来像 manifest 错了，
    # 其实是这行常量过期了。
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != expected:
        raise SystemExit(
            f"扩展 manifest 的版本是 {manifest.get('version')}，"
            f"而 VERSION 文件写的是 {expected}——两者必须一致"
        )
    files = sorted(
        path for path in SOURCE.rglob("*")
        if path.is_file() and path.name not in EXCLUDED and "__pycache__" not in path.parts
    )
    for path in files:
        lowered = path.name.lower()
        if lowered.endswith((".pem", ".key", ".p12", ".env")):
            raise SystemExit(f"secret-like file refused: {path}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(SOURCE).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(json.dumps({"output": str(OUTPUT), "files": len(files), "sha256": digest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
