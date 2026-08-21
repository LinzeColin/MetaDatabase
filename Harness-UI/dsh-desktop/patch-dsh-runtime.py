#!/usr/bin/env python3
"""Add the local normal-app update and personalization bridge to DSH Desktop."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys


APP_MENU_MARK = "260822-normal-app-menu"
UPDATE_MARK = "260822-safe-macos-update"
ICON_MARK = "260822-external-icon-v2"
OLD_ICON_MARK = "260822-external-icon"
SCNET_MARK = 'baseUrl.includes("scnet.cn")'


def replace_once(source: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in source:
        return source, False
    if old not in source:
        raise RuntimeError(f"DSH 运行时代码已变化，无法安全应用 {label} 补丁")
    return source.replace(old, new, 1), True


def patch_runtime(source: str) -> tuple[str, list[str]]:
    changed: list[str] = []

    old_icon = '''\t\tconst icon = nativeImage.createFromPath(spec.iconPath);
\t\tif (icon.isEmpty()) throw new Error(`dsh-plugin-desktop: failed to load application icon ${spec.iconPath}`);'''
    old_external_icon = f'''\t\t/* {OLD_ICON_MARK}: load the user's icon outside the replaceable app bundle. */
\t\tconst personalizedIcon = join(app.getPath("home"), ".dsh", "personalization", "dsh-desktop", "icon.icns");
\t\tconst icon = nativeImage.createFromPath(existsSync(personalizedIcon) ? personalizedIcon : spec.iconPath);
\t\tif (icon.isEmpty()) throw new Error(`dsh-plugin-desktop: failed to load application icon ${{spec.iconPath}}`);'''
    new_icon = f'''\t\t/* {ICON_MARK}: keep Finder's ICNS and use its PNG derivative for Electron at runtime. */
\t\tconst personalizedIcon = join(app.getPath("home"), ".dsh", "personalization", "dsh-desktop", "icon.png");
\t\tconst runtimeIconPath = existsSync(personalizedIcon) ? personalizedIcon : spec.iconPath;
\t\tconst icon = nativeImage.createFromPath(runtimeIconPath);
\t\tif (icon.isEmpty()) throw new Error(`dsh-plugin-desktop: failed to load application icon ${{runtimeIconPath}}`);'''
    if ICON_MARK not in source:
        if old_external_icon in source:
            source = source.replace(old_external_icon, new_icon, 1)
            changed.append("external-icon-v2")
        else:
            source, did_change = replace_once(source, old_icon, new_icon, "外置图标")
            if did_change:
                changed.append("external-icon-v2")

    if UPDATE_MARK not in source:
        method_start = source.find("async downloadAndOpenUpdate(")
        guards = ('\t\tif (this.platform === "darwin") {', '\t\tif (platform === "darwin") {')
        start = next((source.find(guard, method_start) for guard in guards if source.find(guard, method_start) >= 0), -1)
        end_marker = '\n\t\tif ((await dialog.showMessageBox({'
        end = source.find(end_marker, start) if start >= 0 else -1
        if method_start < 0 or start < 0 or end < 0:
            raise RuntimeError("DSH 运行时代码已变化，无法安全定位 macOS 一键安装逻辑")
        old_update = source[start:end]
        if "shell.openPath(artifactPath)" not in old_update or "failed to open update disk image" not in old_update:
            raise RuntimeError("DSH macOS 更新逻辑已变化，拒绝应用未经验证的一键安装补丁")
        guard = old_update.splitlines()[0]
        new_update = f'''{guard}
\t\t\t/* {UPDATE_MARK}: install only after a normal app quit; keep user data outside the bundle. */
\t\t\tconst helper = join(app.getPath("home"), ".dsh", "_patches", "install-dsh-update.py");
\t\t\tif (!existsSync(helper)) throw new Error("dsh-plugin-desktop: safe macOS update helper is missing");
\t\t\tconst zh = this.locale === "zh";
\t\t\tif ((await dialog.showMessageBox({{
\t\t\t\ttype: "question",
\t\t\t\ttitle: zh ? "DSH Desktop 更新已下载" : "DSH Desktop Update Downloaded",
\t\t\t\tmessage: zh ? `现在退出并安装 DSH Desktop ${{version}}？` : `Quit and install DSH Desktop ${{version}} now?`,
\t\t\t\tdetail: zh ? "只替换应用本体；图标、皮肤、配置、会话和 HarnessUI 素材保持不变。安装失败会保留旧版。" : "Only the app bundle is replaced. Icon, skins, settings, sessions, and HarnessUI assets stay in place.",
\t\t\t\tbuttons: zh ? ["退出并安装", "稍后"] : ["Quit and Install", "Later"],
\t\t\t\tdefaultId: 0,
\t\t\t\tcancelId: 1,
\t\t\t\tnoLink: true
\t\t\t}})).response !== 0) return;
\t\t\tconst spec = this.scheduled;
\t\t\tif (spec === void 0) throw new Error("dsh-plugin-desktop: no active shell can exit for update installation");
\t\t\tsignal.throwIfAborted();
\t\t\tconst child = spawn("/usr/bin/python3", [helper, "--pid", String(process.pid), "--artifact", artifactPath, "--version", version], {{ detached: true, stdio: "ignore" }});
\t\t\tchild.unref();
\t\t\tthis.quitting = true;
\t\t\tspec.requestQuit(0);
\t\t\treturn;
\t\t}}'''
        source = source[:start] + new_update + source[end:]
        changed.append("safe-update")

    modern_menu = '''\tbuildApplicationMenuItems() {
\t\tconst tools = this.contributedTrayItems("tools");
\t\tconst profiles = this.contributedTrayItems("profiles");
\t\tconst items = [];
\t\tif (tools.length > 0) items.push(...tools);
\t\tif (tools.length > 0 && profiles.length > 0) items.push({ type: "separator" });
\t\tif (profiles.length > 0) items.push(...profiles);
\t\treturn items;
\t}'''
    modern_menu_patched = f'''\tbuildApplicationMenuItems() {{
\t\t/* {APP_MENU_MARK}: include update/status commands in the upstream native app menu. */
\t\tconst tools = this.contributedTrayItems("tools");
\t\tconst profiles = this.contributedTrayItems("profiles");
\t\tconst status = this.contributedTrayItems("status");
\t\tconst zh = this.locale === "zh";
\t\tconst items = [];
\t\tif (tools.length > 0) items.push(...tools);
\t\tif (tools.length > 0 && profiles.length > 0) items.push({{ type: "separator" }});
\t\tif (profiles.length > 0) items.push(...profiles);
\t\tif (items.length > 0 && status.length > 0) items.push({{ type: "separator" }});
\t\tif (status.length > 0) items.push(...status);
\t\titems.push({{ type: "separator" }},
\t\t\t{{ label: zh ? `当前版本：${{PRODUCT_VERSION}}` : `Current Version: ${{PRODUCT_VERSION}}`, enabled: false }},
\t\t\t{{ label: zh ? "个性化：外置保存，更新时保留" : "Personalization: preserved outside the app", enabled: false }});
\t\treturn items;
\t}}'''
    old_menu_marker = "\t\t/* 260821-macos-update-app-menu：复用官方托盘 updater，把同一个命令放进普通应用菜单。 */"
    old_menu_end = "\t\t}\n\t\tconst template = [{"
    if APP_MENU_MARK not in source:
        if modern_menu in source:
            source = source.replace(modern_menu, modern_menu_patched, 1)
            changed.append("app-menu")
        elif old_menu_marker in source:
            start = source.index(old_menu_marker)
            end = source.index(old_menu_end, start) + len("\t\t}\n")
            source = source[:start] + _menu_block() + source[end:]
            changed.append("app-menu")
        elif 'Menu.setApplicationMenu(Menu.buildFromTemplate' not in source[source.index('const status = this.contributedTrayItems("status");'):]:
            old = '\t\tconst status = this.contributedTrayItems("status");\n\t\tconst template = [{'
            new = '\t\tconst status = this.contributedTrayItems("status");\n' + _menu_block() + '\t\tconst template = [{'
            source, did_change = replace_once(source, old, new, "应用菜单")
            if did_change:
                changed.append("app-menu")

    return source, changed


def _menu_block() -> str:
    return f'''\t\t/* {APP_MENU_MARK}: mirror the live updater command into the normal macOS app menu. */
\t\tif (this.platform === "darwin") {{
\t\t\tconst zh = this.locale === "zh";
\t\t\tMenu.setApplicationMenu(Menu.buildFromTemplate([{{
\t\t\t\tlabel: spec.productName,
\t\t\t\tsubmenu: [
\t\t\t\t\t{{ role: "about", label: zh ? "关于 DSH Desktop" : "About DSH Desktop" }},
\t\t\t\t\t{{ type: "separator" }},
\t\t\t\t\t...status,
\t\t\t\t\t{{ label: zh ? `当前版本：${{PRODUCT_VERSION}}` : `Current Version: ${{PRODUCT_VERSION}}`, enabled: false }},
\t\t\t\t\t{{ label: zh ? "个性化：外置保存，更新时保留" : "Personalization: preserved outside the app", enabled: false }},
\t\t\t\t\t{{ type: "separator" }},
\t\t\t\t\t{{ role: "services" }},
\t\t\t\t\t{{ type: "separator" }},
\t\t\t\t\t{{ role: "hide", label: zh ? "隐藏 DSH Desktop" : "Hide DSH Desktop" }},
\t\t\t\t\t{{ role: "hideOthers", label: zh ? "隐藏其他应用" : "Hide Others" }},
\t\t\t\t\t{{ role: "unhide", label: zh ? "全部显示" : "Show All" }},
\t\t\t\t\t{{ type: "separator" }},
\t\t\t\t\t{{ label: zh ? "退出 DSH Desktop" : "Quit DSH Desktop", click: () => {{ spec.requestQuit(0); }} }}
\t\t\t\t]
\t\t\t}}, {{ role: "fileMenu" }}, {{ role: "editMenu" }}, {{ role: "viewMenu" }}, {{ role: "windowMenu" }}]));
\t\t}}
'''


def patch_scnet(app: pathlib.Path, backup: bool) -> bool:
    target = app / "Contents/Resources/app.asar.unpacked/node_modules/@earendil-works/pi-ai/dist/api/openai-completions.js"
    if not target.is_file():
        raise RuntimeError("DSH 包内未找到 pi-ai OpenAI 适配器")
    source = target.read_text()
    if SCNET_MARK in source:
        return False
    old = "    const isNonStandard = isNvidia ||\n"
    new = '    const isNonStandard = isNvidia ||\n        baseUrl.includes("scnet.cn") ||\n'
    if old not in source:
        raise RuntimeError("pi-ai 兼容性代码已变化，SCNet 补丁需要更新")
    if backup:
        shutil.copy2(target, target.with_suffix(".js.bak-normal-app"))
    target.write_text(source.replace(old, new, 1))
    return True


def patch_app(app: pathlib.Path, backup: bool = True) -> list[str]:
    lib = app / "Contents/Resources/app.asar.unpacked/lib"
    targets = [candidate for candidate in lib.glob("electron-runtime-*.js") if "rebuildTrayMenu()" in candidate.read_text()]
    if len(targets) != 1:
        raise RuntimeError(f"需要唯一的 Electron runtime，实际找到 {len(targets)} 个")
    target = targets[0]
    source = target.read_text()
    patched, changes = patch_runtime(source)
    if patched != source:
        if backup:
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak-normal-app"))
        target.write_text(patched)
    if patch_scnet(app, backup):
        changes.append("scnet-system-role")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=pathlib.Path, default=pathlib.Path("/Applications/DSH Desktop.app"))
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    try:
        changes = patch_app(args.app.resolve(), backup=not args.no_backup)
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    print("已应用：" + (", ".join(changes) if changes else "无需变更"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
