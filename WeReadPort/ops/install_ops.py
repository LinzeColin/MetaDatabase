#!/usr/bin/env python3
"""准备或激活“微信读书笔记迁移”的版本化 OVH 非用户数据运维平面。"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import pwd
import shutil
import subprocess
import sys
from urllib.parse import urlparse

VERSION = "0.0.0.1.3"
UNITS = (
    "weread-port-ops-monitor.timer",
    "weread-port-ops-private-sync.timer",
    "weread-port-ops-backup.timer",
    "weread-port-ops-purge.timer",
    "weread-port-ops-restore-check.timer",
)


def copy_tree(source: pathlib.Path, target: pathlib.Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        copy_function=shutil.copy2,
    )
    for path in (target / "bin").glob("*"):
        path.chmod(0o755)


def root_path(root: pathlib.Path, absolute: str) -> pathlib.Path:
    return root / absolute.lstrip("/")


def validate_inputs(site_url: str, private_client: str) -> None:
    if site_url:
        parsed = urlparse(site_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or any(char.isspace() for char in site_url):
            raise ValueError("--site-url 必须是无凭证、查询、片段和空白字符的纯 HTTPS 源地址")
        if parsed.path not in {"", "/"}:
            raise ValueError("--site-url 必须是源地址，不能包含路径")
    if private_client:
        if any(char in private_client for char in ("\n", "\r", "\x00")):
            raise ValueError("--private-db-client 包含禁止的控制字符")
        if not pathlib.Path(private_client).is_absolute():
            raise ValueError("--private-db-client 必须是绝对路径")


def update_env(path: pathlib.Path, template: pathlib.Path, site_url: str, private_client: str) -> None:
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = template.read_text(encoding="utf-8")
    replacements = {}
    if site_url:
        replacements["WEREAD_PORT_SITE_URL"] = site_url
    if private_client:
        replacements["WEREAD_PORT_PRIVATE_DB_CLIENT"] = private_client
    lines = []
    seen = set()
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in replacements:
                line = f"{key}={replacements[key]}"
                seen.add(key)
        lines.append(line)
    for key, value in replacements.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o600)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("/"), help="文件系统根目录；有限安装验证时可使用临时目录")
    parser.add_argument("--site-url", default="")
    parser.add_argument("--private-db-client", default="")
    parser.add_argument("--status-collector", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true", help="当根目录为真实文件系统时激活 systemd")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    validate_inputs(args.site_url, args.private_db_client)
    source = pathlib.Path(__file__).resolve().parent
    release = root_path(root, f"/opt/weread-port-ops/releases/{VERSION}")
    current = root_path(root, "/opt/weread-port-ops/current")
    state = root_path(root, "/var/lib/weread-port-ops")
    env_file = root_path(root, "/etc/weread-port/ops.env")
    unit_dir = root_path(root, "/etc/systemd/system")
    adapter_dir = root_path(root, "/srv/linze/apps/status/data/external-projects")

    copy_tree(source, release)
    current.parent.mkdir(parents=True, exist_ok=True)
    if current.is_symlink() or current.exists():
        current.unlink() if current.is_symlink() or current.is_file() else shutil.rmtree(current)
    current.symlink_to(pathlib.Path("releases") / VERSION)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    adapter_dir.mkdir(parents=True, exist_ok=True)
    adapter_file = adapter_dir / "weread-port.json"
    status_file = state / "public-status.json"
    adapter_exists = os.path.lexists(adapter_file)
    if adapter_exists:
        if adapter_file.is_symlink() and os.readlink(adapter_file) == str(status_file):
            pass
        elif adapter_file.is_file() and not args.apply:
            # 有限安装验证时保留合成根目录夹具。
            pass
        else:
            adapter_file.unlink()
            adapter_exists = False
    if not os.path.lexists(adapter_file):
        adapter_file.symlink_to(status_file)

    update_env(env_file, source / "env/weread-port-ops.env.example", args.site_url, args.private_db_client)
    unit_dir.mkdir(parents=True, exist_ok=True)
    for item in sorted((source / "systemd").iterdir()):
        if item.is_file():
            shutil.copy2(item, unit_dir / item.name)
            (unit_dir / item.name).chmod(0o644)

    status_patch = None
    if args.status_collector:
        command = [sys.executable, str(source / "status/install_status_adapter.py"), str(args.status_collector)]
        if args.apply:
            command.append("--apply")
        status_patch = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if status_patch.returncode != 0:
            raise RuntimeError(status_patch.stderr.strip() or status_patch.stdout.strip())

    activated = False
    if args.apply and root == pathlib.Path("/"):
        if os.geteuid() != 0:
            raise PermissionError("在真实文件系统使用 --apply 需要 root 权限")
        try:
            pwd.getpwnam("weread-port-ops")
        except KeyError:
            run(["useradd", "--system", "--home", "/var/lib/weread-port-ops", "--shell", "/usr/sbin/nologin", "weread-port-ops"])
        run(["chown", "-R", "weread-port-ops:weread-port-ops", str(state)])
        run(["systemctl", "daemon-reload"])
        run(["runuser", "-u", "weread-port-ops", "--", str(current / "bin/weread-port-ops"), "init"])
        run(["systemctl", "enable", "--now", *UNITS])
        run(["systemctl", "start", "weread-port-ops-monitor.service"])
        activated = True

    result = {
        "status": "activated" if activated else "prepared",
        "version": VERSION,
        "release": str(release),
        "current": str(current),
        "environment": str(env_file),
        "state": str(state),
        "statusAdapter": str(adapter_file),
        "statusCollectorPatched": json.loads(status_patch.stdout) if status_patch else None,
        "units": list(UNITS),
        "nextCommand": None if activated else 'sudo python3 ops/install_ops.py --apply --site-url "$PRODUCTION_ORIGIN"',
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"运维平面安装失败：{exc}", file=sys.stderr)
        raise SystemExit(2)
