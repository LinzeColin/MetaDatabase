#!/usr/bin/env python3
"""把阅迁 v0.0.0.1.8 账户服务准备为可回滚的 systemd 版本化发布。"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import pwd
import secrets
import shutil
import subprocess
import sys

VERSION = "0.0.0.1.8"
UNITS = (
    "weread-port-platform.service",
    "weread-port-import-worker.service",
    "weread-port-platform-health.timer",
    "weread-port-platform-backup.timer",
    "weread-port-facts-sync.timer",
)
OPTIONAL_UNITS = ("weread-port-r2-oci-backup.timer",)
REQUIRED_DEPLOY_KEYS = (
    "WRP_SESSION_PEPPER", "WRP_CREDENTIAL_PEPPER", "WRP_KEYRING_JSON", "WRP_ACTIVE_KEY_ID",
    "WRP_INTERNAL_PROXY_SECRET", "WRP_R2_ENDPOINT", "WRP_R2_BUCKET", "WRP_R2_ACCESS_KEY_ID",
    "WRP_R2_SECRET_ACCESS_KEY", "WRP_GOOGLE_CLIENT_ID", "WRP_GOOGLE_CLIENT_SECRET",
    "WRP_GITHUB_CLIENT_ID", "WRP_GITHUB_CLIENT_SECRET", "WRP_NOTION_CLIENT_ID",
    "WRP_NOTION_CLIENT_SECRET", "WRP_PRIVATE_DATABASE_WORKTREE",
)


def root_path(root: pathlib.Path, absolute: str) -> pathlib.Path:
    return root / absolute.lstrip("/")


def copy_release(source_root: pathlib.Path, target: pathlib.Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in ("service", "package.json", "AGENTS.md"):
        source = source_root / name
        destination = target / name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        else:
            shutil.copy2(source, destination)
    for script in (target / "service/scripts").glob("*.py"):
        script.chmod(0o755)


def read_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(path: pathlib.Path, template: pathlib.Path, *, generate: bool) -> dict[str, str]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, path)
    values = read_env(path)
    generated: dict[str, str] = {}
    if generate:
        for key in ("WRP_SESSION_PEPPER", "WRP_CREDENTIAL_PEPPER", "WRP_INTERNAL_PROXY_SECRET"):
            if not values.get(key):
                generated[key] = base64.b64encode(secrets.token_bytes(32)).decode("ascii") if key != "WRP_INTERNAL_PROXY_SECRET" else secrets.token_urlsafe(48)
        if not values.get("WRP_KEYRING_JSON"):
            generated["WRP_KEYRING_JSON"] = json.dumps({"k1": base64.b64encode(secrets.token_bytes(32)).decode("ascii")}, separators=(",", ":"))
    if generated:
        lines = path.read_text(encoding="utf-8").splitlines()
        output: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if "=" in line and not line.lstrip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                if key in generated:
                    line = f"{key}={generated[key]}"
                    seen.add(key)
            output.append(line)
        for key, value in generated.items():
            if key not in seen:
                output.append(f"{key}={value}")
        path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o600)
    return read_env(path)



def run_preflight(source_root: pathlib.Path, env_file: pathlib.Path, *, strict: bool, require_paths: bool) -> dict:
    command = [sys.executable, str(source_root / "service/scripts/platform_preflight.py"), "--env-file", str(env_file)]
    if strict:
        command.append("--strict")
    if require_paths:
        command.append("--require-paths")
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PREFLIGHT_OUTPUT_INVALID") from exc
    payload["exitCode"] = completed.returncode
    return payload

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("/"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--enable-oci-backup", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    source_root = pathlib.Path(__file__).resolve().parents[1]
    release = root_path(root, f"/opt/weread-port/releases/{VERSION}")
    current = root_path(root, "/opt/weread-port/current")
    env_file = root_path(root, "/etc/weread-port/platform.env")
    unit_dir = root_path(root, "/etc/systemd/system")
    state = root_path(root, "/var/lib/weread-port")

    copy_release(source_root, release)
    current.parent.mkdir(parents=True, exist_ok=True)
    if current.is_symlink() or current.is_file(): current.unlink()
    elif current.exists(): shutil.rmtree(current)
    current.symlink_to(pathlib.Path("releases") / VERSION)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    values = write_env(env_file, source_root / "service/env/weread-port-platform.env.example", generate=args.apply and root == pathlib.Path("/"))
    unit_dir.mkdir(parents=True, exist_ok=True)
    for unit in sorted((source_root / "service/systemd").iterdir()):
        shutil.copy2(unit, unit_dir / unit.name)
        (unit_dir / unit.name).chmod(0o644)

    missing = [key for key in REQUIRED_DEPLOY_KEYS if not values.get(key)]
    if args.enable_oci_backup:
        missing += [key for key in ("WRP_R2_RCLONE_SOURCE", "WRP_OCI_RCLONE_TARGET") if not values.get(key)]
    preflight = run_preflight(source_root, env_file, strict=args.apply and root == pathlib.Path("/"), require_paths=args.apply and root == pathlib.Path("/"))
    activated = False
    if args.apply and root == pathlib.Path("/"):
        if os.geteuid() != 0:
            raise PermissionError("--apply 需要 root")
        if missing or preflight.get("status") != "PASS":
            print(json.dumps({
                "status": "INPUT_REQUIRED",
                "missing": sorted(set(missing)),
                "preflight": preflight,
                "environment": str(env_file),
                "next": "仅补齐列出的 Owner 输入后原命令重试；不得修改版本或产品代码",
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 3
        try: pwd.getpwnam("weread-port")
        except KeyError: subprocess.run(["useradd", "--system", "--home", "/var/lib/weread-port", "--shell", "/usr/sbin/nologin", "weread-port"], check=True)
        subprocess.run(["chown", "-R", "weread-port:weread-port", str(state), str(release)], check=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        units = [*UNITS, *(OPTIONAL_UNITS if args.enable_oci_backup else ())]
        subprocess.run(["systemctl", "enable", "--now", *units], check=True)
        subprocess.run(["systemctl", "start", "weread-port-platform-health.service"], check=True)
        activated = True

    print(json.dumps({
        "status": "ACTIVATED" if activated else "PREPARED",
        "version": f"v{VERSION}",
        "release": str(release),
        "current": str(current),
        "environment": str(env_file),
        "missingDeploymentInputs": sorted(set(missing)),
        "preflight": preflight,
        "units": [*UNITS, *(OPTIONAL_UNITS if args.enable_oci_backup else ())],
        "nextCommand": None if activated else "sudo python3 service/install_platform.py --apply",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"账户平台安装失败：{exc}", file=sys.stderr)
        raise SystemExit(2)
