#!/usr/bin/env python3
"""Install a downloaded stable DSH Desktop DMG after the current app exits."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time


BUNDLE_ID = "ai.deepseek.dsh.desktop"
TARGET = pathlib.Path("/Applications/DSH Desktop.app")
DSH_HOME = pathlib.Path.home() / ".dsh"
UPDATES = DSH_HOME / "desktop-updates"
PATCHER = DSH_HOME / "_patches" / "patch-dsh-runtime.py"
ICON = DSH_HOME / "personalization" / "dsh-desktop" / "icon.icns"
RUNTIME_ICON = DSH_HOME / "personalization" / "dsh-desktop" / "icon.png"


def run(*args: str, capture: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=capture, timeout=timeout)


def write_receipt(status: str, version: str, detail: str, rollback: pathlib.Path | None = None) -> None:
    UPDATES.mkdir(parents=True, exist_ok=True)
    value = {
        "version": 1,
        "status": status,
        "desktopVersion": version,
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "detail": detail,
        "rollbackApp": str(rollback) if rollback else None,
        "preservedRoots": [str(DSH_HOME), str(pathlib.Path.home() / ".harness-ui")],
    }
    temporary = UPDATES / "last-update.json.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(UPDATES / "last-update.json")


def wait_for_exit(pid: int) -> None:
    for _ in range(240):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.5)
    raise RuntimeError("DSH Desktop 未在两分钟内正常退出")


def ensure_runtime_icon() -> None:
    """Create the PNG Electron can decode without changing the user's ICNS."""
    if RUNTIME_ICON.is_file():
        return
    temporary = RUNTIME_ICON.with_name("icon.runtime.tmp.png")
    run("/usr/bin/sips", "-s", "format", "png", str(ICON), "--out", str(temporary))
    temporary.replace(RUNTIME_ICON)


def mounted_app(artifact: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    mount = pathlib.Path(tempfile.mkdtemp(prefix="dsh-update-mount-"))
    try:
        # The app has already verified the downloaded artifact and we validate the
        # mounted bundle with codesign + Gatekeeper below. A fixed mount point and
        # no auto-open avoid DiskImages post-exec hangs seen with `-plist`.
        run(
            "/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-noverify", "-noautoopen",
            "-mountpoint", str(mount), str(artifact), capture=True, timeout=240,
        )
        for candidate in mount.glob("*.app"):
            info = plistlib.loads((candidate / "Contents/Info.plist").read_bytes())
            if info.get("CFBundleIdentifier") == BUNDLE_ID:
                return candidate, mount
    except Exception:
        subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if mount.exists():
            try:
                mount.rmdir()
            except OSError:
                pass
        raise
    subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if mount.exists():
        try:
            mount.rmdir()
        except OSError:
            pass
    raise RuntimeError("下载的 DMG 中没有 DSH Desktop.app")


def install(pid: int, artifact: pathlib.Path, version: str) -> pathlib.Path:
    if not artifact.is_absolute() or artifact.suffix.lower() != ".dmg" or not artifact.is_file():
        raise RuntimeError("更新文件不是有效的绝对 DMG 路径")
    if not PATCHER.is_file() or not ICON.is_file():
        raise RuntimeError("缺少 DSH 更新补丁或外置图标，旧版保持不变")
    ensure_runtime_icon()
    wait_for_exit(pid)
    candidate, mount = mounted_app(artifact)
    stage_root: pathlib.Path | None = None
    rollback: pathlib.Path | None = None
    try:
        info = plistlib.loads((candidate / "Contents/Info.plist").read_bytes())
        actual_version = str(info.get("CFBundleShortVersionString", ""))
        if actual_version != version:
            raise RuntimeError(f"DMG 版本与更新服务不一致：{actual_version} / {version}")
        run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(candidate))
        run("/usr/sbin/spctl", "--assess", "--type", "execute", str(candidate))

        stage_root = pathlib.Path(tempfile.mkdtemp(prefix=".dsh-update-", dir=str(TARGET.parent)))
        staged = stage_root / TARGET.name
        run("/usr/bin/ditto", str(candidate), str(staged))
        run("/usr/bin/python3", str(PATCHER), "--app", str(staged), "--no-backup")
        shutil.copy2(ICON, staged / "Contents/Resources/icon.icns")
        run("/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(staged))
        run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(staged))

        rollback = UPDATES / "rollback" / f"{version}-{int(time.time())}" / TARGET.name
        rollback.parent.mkdir(parents=True, exist_ok=True)
        if TARGET.exists():
            TARGET.replace(rollback)
        try:
            staged.replace(TARGET)
        except Exception:
            if rollback.exists() and not TARGET.exists():
                rollback.replace(TARGET)
            raise
        run("/usr/bin/open", str(TARGET))
        write_receipt("installed", version, "应用本体已替换；外置图标、配置、皮肤、会话与 HarnessUI 数据保持原位。", rollback)
        return rollback
    finally:
        subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if mount.exists():
            try:
                mount.rmdir()
            except OSError:
                pass
        if stage_root and stage_root.exists():
            shutil.rmtree(stage_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--artifact", type=pathlib.Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        install(args.pid, args.artifact.resolve(), args.version)
    except Exception as error:
        write_receipt("failed", args.version, str(error))
        try:
            run("/usr/bin/open", str(TARGET))
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
