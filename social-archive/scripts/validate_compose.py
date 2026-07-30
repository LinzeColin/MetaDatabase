from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _declared_env_files(document: dict[object, object], root: Path) -> list[Path]:
    files: list[Path] = []
    for service in document.get("services", {}).values():
        if not isinstance(service, dict):
            continue
        declared = service.get("env_file")
        entries = declared if isinstance(declared, list) else [declared]
        for entry in entries:
            name = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(name, str) and name:
                files.append(root / name)
    return files


def main(path: str, *, static: bool = False) -> int:
    compose_file = Path(path)
    if not compose_file.exists():
        print(f"Compose 文件不存在：{compose_file}", file=sys.stderr)
        return 2
    try:
        import yaml

        document = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("services"), dict) or not document["services"]:
            raise ValueError("services 缺失")
    except Exception as exc:
        print(f"Compose YAML 无效：{exc}", file=sys.stderr)
        return 1

    missing_env_files = [file for file in _declared_env_files(document, compose_file.parent) if not file.is_file()]
    if missing_env_files:
        names = ", ".join(dict.fromkeys(file.name for file in missing_env_files))
        print(f"PASS：{compose_file} 结构有效；Owner 配置 {names} 缺失，跳过 Docker Compose 渲染。")
        return 0

    if not static and shutil.which("docker"):
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "config", "--quiet"],
            cwd=compose_file.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return result.returncode
    print(f"PASS：{compose_file} 结构有效。")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a Compose file without starting services")
    parser.add_argument("--static", action="store_true", help="只解析 YAML；绝不调用 Docker")
    parser.add_argument("path", nargs="?", default="compose.yaml")
    args = parser.parse_args()
    raise SystemExit(main(args.path, static=args.static))
