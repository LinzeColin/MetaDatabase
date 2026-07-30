#!/usr/bin/env python3
"""Social Archive 中文部署向导。

该向导只写入项目内 .env 与 runtime/secrets，绝不打印 Secret。
真实授权仍由扩展/服务端 Probe 证明；配置存在不等于已连接。
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
from pathlib import Path
from urllib.parse import urlparse

ENV_KEYS = {
    "SOCIAL_ARCHIVE_PUBLIC_BASE_URL",
    "SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL",
    "SOCIAL_ARCHIVE_GITHUB_MARKDOWN_REPOSITORY",
    "SOCIAL_ARCHIVE_GITHUB_MARKDOWN_BRANCH",
    "SOCIAL_ARCHIVE_NOTION_DATA_SOURCE_ID",
    "SOCIAL_ARCHIVE_NOTION_DATABASE_ID",
    "SOCIAL_ARCHIVE_OBSIDIAN_VAULT_ROOT",
    "SOCIAL_ARCHIVE_OBSIDIAN_REST_URL",
    "SOCIAL_ARCHIVE_OBSIDIAN_REST_CA_FILE",
    "SOCIAL_ARCHIVE_KARAKEEP_URL",
    "SOCIAL_ARCHIVE_LINKWARDEN_URL",
}


def valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return lines, values


def write_env(path: Path, updates: dict[str, str]) -> None:
    lines, _ = read_env(path)
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        if line and not line.lstrip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)
    if remaining:
        if output and output[-1] != "":
            output.append("")
        output.append("# 由 Social Archive 中文向导写入")
        for key in sorted(remaining):
            output.append(f"{key}={remaining[key]}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8")
    path.chmod(0o600)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}：").strip()
    return value or default


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{marker}]：").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "是", "好", "1"}


def ensure_repo(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("GitHub 仓库必须是 owner/repo 格式")
    return value


def interactive(root: Path) -> None:
    env_path = root / ".env"
    template = root / ".env.example"
    if not env_path.exists() and template.exists():
        env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    _, current = read_env(env_path)
    updates: dict[str, str] = {}

    print("\nSocial Archive 首次部署向导")
    print("只需回答看得懂的问题；留空会采用安全默认值。填写后仍会主动检查连接。\n")

    api_url = ask("扩展访问的 API 地址", current.get("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "http://127.0.0.1:8765"))
    library_url = ask("打开档案馆的网址", current.get("SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL", api_url))
    if not valid_http_url(api_url) or not valid_http_url(library_url):
        raise ValueError("服务地址必须是完整的 http:// 或 https:// URL")
    updates["SOCIAL_ARCHIVE_PUBLIC_BASE_URL"] = api_url.rstrip("/")
    updates["SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL"] = library_url.rstrip("/")

    if ask_yes_no("现在连接 GitHub 私有 Markdown 目的地"):
        repository = ensure_repo(ask("Private Repository（owner/repo）"))
        token = getpass.getpass("GitHub Fine-grained Token（输入不会显示）：").strip()
        if not token:
            raise ValueError("GitHub Token 不能为空")
        updates["SOCIAL_ARCHIVE_GITHUB_MARKDOWN_REPOSITORY"] = repository
        updates["SOCIAL_ARCHIVE_GITHUB_MARKDOWN_BRANCH"] = ask("写入分支", "main")
        write_secret(root / "runtime/secrets/github_token", token)

    if ask_yes_no("现在连接 Notion"):
        token = getpass.getpass("Notion Integration Secret（输入不会显示）：").strip()
        if not token:
            raise ValueError("Notion Secret 不能为空")
        target = ask("Notion data_source_id（不知道可先留空）")
        database = "" if target else ask("兼容 database_id（服务会发现唯一数据源，可留空）")
        if target:
            updates["SOCIAL_ARCHIVE_NOTION_DATA_SOURCE_ID"] = target
        if database:
            updates["SOCIAL_ARCHIVE_NOTION_DATABASE_ID"] = database
        write_secret(root / "runtime/secrets/notion_token", token)


    if ask_yes_no("现在连接 Karakeep 阅读器"):
        updates["SOCIAL_ARCHIVE_KARAKEEP_URL"] = ask("Karakeep 服务地址", current.get("SOCIAL_ARCHIVE_KARAKEEP_URL", "http://karakeep:3000")).rstrip("/")
        token = getpass.getpass("Karakeep API Key（输入不会显示）：").strip()
        if not token:
            raise ValueError("Karakeep API Key 不能为空")
        write_secret(root / "runtime/secrets/karakeep_api_token", token)

    if ask_yes_no("现在连接 Linkwarden 阅读器"):
        updates["SOCIAL_ARCHIVE_LINKWARDEN_URL"] = ask("Linkwarden 服务地址", current.get("SOCIAL_ARCHIVE_LINKWARDEN_URL", "http://linkwarden:3000")).rstrip("/")
        token = getpass.getpass("Linkwarden Token（输入不会显示）：").strip()
        if not token:
            raise ValueError("Linkwarden Token 不能为空")
        write_secret(root / "runtime/secrets/linkwarden_api_token", token)

    if ask_yes_no("服务器可以直接访问一个 Obsidian Vault 目录"):
        vault = ask("Vault 绝对路径")
        if not Path(vault).is_absolute():
            raise ValueError("Vault 必须填写绝对路径")
        updates["SOCIAL_ARCHIVE_OBSIDIAN_VAULT_ROOT"] = vault

    write_env(env_path, updates)
    print("\n配置已保存。下一步运行：bash scripts/start.sh")
    print("扩展配对后，请在设置页点击“检查全部连接”；只有实测通过才会显示已连接。")
    print("本机 Obsidian 推荐安装 apps/obsidian-plugin，不需要 macOS 常驻任务。")


def validate_non_interactive(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.exists():
        template = root / ".env.example"
        if template.exists():
            env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text("", encoding="utf-8")
    lines, values = read_env(env_path)
    unknown = sorted(key for key in values if key.startswith("SOCIAL_ARCHIVE_") and key not in ENV_KEYS and key.endswith(("PUBLIC_BASE_URL", "PUBLIC_LIBRARY_URL")))
    if unknown:
        raise ValueError(f"发现无法识别的关键 URL 配置：{', '.join(unknown)}")
    for key in ("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL"):
        if values.get(key) and not valid_http_url(values[key]):
            raise ValueError(f"{key} 不是完整 URL")
    secrets_root = root / "runtime/secrets"
    secrets_root.mkdir(parents=True, exist_ok=True)
    os.chmod(secrets_root, 0o700)
    for path in secrets_root.iterdir():
        if path.is_file():
            path.chmod(0o600)
    assert lines is not None
    print("向导非交互预检通过；未执行外部连接或生产变更。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Social Archive 中文首次部署向导")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--non-interactive", action="store_true", help="只校验和修复本地文件权限，不询问凭据")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.non_interactive:
            validate_non_interactive(root)
        else:
            interactive(root)
    except (ValueError, OSError, KeyboardInterrupt) as exc:
        print(f"向导停止：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
