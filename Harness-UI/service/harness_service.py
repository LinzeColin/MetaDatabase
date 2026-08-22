#!/usr/bin/env python3
"""Loopback HarnessUI catalogue, state, gallery, and SMB asset service."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import pathlib
import random
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


GAMES = {
    "原神": "genshin",
    "崩铁": "hsr",
    "绝区零": "zzz",
    "鸣潮": "wuwa",
    "异环": "nte",
}
MAX_BODY = 1024 * 1024
WRITABLE = {"mode", "selected", "intervalMs", "hidden", "cycle", "cursor", "lastRotate"}


def atomic_json(file: pathlib.Path, value: object) -> None:
    temporary = file.with_suffix(file.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(file)


def read_json(file: pathlib.Path, fallback: object) -> object:
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def child_directories(root: pathlib.Path) -> list[pathlib.Path]:
    try:
        return sorted((entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith(".")), key=lambda entry: entry.name)
    except OSError:
        return []


def source_assets(source: pathlib.Path) -> tuple[list[dict[str, object]], int, dict[str, int]]:
    assets: list[dict[str, object]] = []
    recognized_games = 0
    game_counts = {game: 0 for game in GAMES.values()}
    if not source.is_dir():
        return assets, recognized_games, game_counts
    for game_name, game in GAMES.items():
        game_root = source / game_name
        if game_root.is_dir():
            recognized_games += 1
        for character_root in child_directories(game_root):
            for variant_root in child_directories(character_root / "skins"):
                light = variant_root / "light.png"
                dark = variant_root / "dark.png"
                if not light.is_file() or not dark.is_file():
                    continue
                meta = read_json(variant_root / "meta.json", {})
                assets.append({
                    "gameName": game_name,
                    "game": game,
                    "character": character_root.name,
                    "variant": variant_root.name,
                    "light": light,
                    "dark": dark,
                    "meta": meta if isinstance(meta, dict) else {},
                    "metaFile": variant_root / "meta.json",
                })
                game_counts[game] += 1
    return assets, recognized_games, game_counts


def fallback_assets(fallback_root: pathlib.Path | None) -> list[dict[str, object]]:
    assets: list[dict[str, object]] = []
    if not fallback_root or not fallback_root.is_dir():
        return assets
    reverse_games = {game: game_name for game_name, game in GAMES.items()}
    for game, game_name in reverse_games.items():
        for character_root in child_directories(fallback_root / game):
            for variant_root in child_directories(character_root):
                light = variant_root / "light.png"
                dark = variant_root / "dark.png"
                if not light.is_file() or not dark.is_file():
                    continue
                meta = read_json(variant_root / "meta.json", {})
                assets.append({
                    "gameName": game_name,
                    "game": game,
                    "character": character_root.name,
                    "variant": variant_root.name,
                    "light": light,
                    "dark": dark,
                    "meta": meta if isinstance(meta, dict) else {},
                    "metaFile": variant_root / "meta.json",
                })
    return assets


def asset_identifier(asset: dict[str, object]) -> str:
    return f"{asset['game']}/{asset['character']}/{asset['variant']}"


def copy_required(source: pathlib.Path, destination: pathlib.Path) -> bool:
    try:
        source_stat = source.stat()
        destination_stat = destination.stat()
        return source_stat.st_size != destination_stat.st_size or source_stat.st_mtime_ns > destination_stat.st_mtime_ns
    except OSError:
        return True


def deploy_source_assets(assets: list[dict[str, object]], fallback_root: pathlib.Path | None) -> int:
    if not fallback_root:
        return 0
    changed: set[str] = set()
    fallback_root.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        destination = fallback_root / str(asset["game"]) / str(asset["character"]) / str(asset["variant"])
        destination.mkdir(parents=True, exist_ok=True)
        for side in ("light", "dark"):
            source_file = pathlib.Path(asset[side])
            target_file = destination / f"{side}.png"
            if not copy_required(source_file, target_file):
                continue
            staged = target_file.with_suffix(".png.sync")
            shutil.copy2(source_file, staged)
            staged.replace(target_file)
            changed.add(asset_identifier(asset))
        source_meta = pathlib.Path(asset["metaFile"])
        target_meta = destination / "meta.json"
        if source_meta.is_file() and copy_required(source_meta, target_meta):
            staged_meta = target_meta.with_suffix(".json.sync")
            shutil.copy2(source_meta, staged_meta)
            staged_meta.replace(target_meta)
            changed.add(asset_identifier(asset))
    return len(changed)


def native_source_sync(helper_url: str | None) -> dict[str, object] | None:
    if not helper_url:
        return None
    request = urllib.request.Request(
        helper_url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            return None
        value = json.loads(raw)
        source_ids = value.get("sourceIds")
        game_counts = value.get("gameCounts")
        deployed = value.get("deployedCount")
        if not isinstance(source_ids, list) or not all(isinstance(identifier, str) for identifier in source_ids):
            return None
        if not isinstance(game_counts, dict) or not all(game in game_counts and isinstance(game_counts[game], int) for game in GAMES.values()):
            return None
        if not isinstance(deployed, int) or deployed < 0:
            return None
        return {"sourceIds": source_ids, "gameCounts": game_counts, "deployedCount": deployed}
    except (OSError, ValueError, urllib.error.URLError):
        return None


def synchronize_catalog(
    source: pathlib.Path,
    base_url: str,
    fallback_root: pathlib.Path | None = None,
    previous: dict[str, object] | None = None,
    now: dt.datetime | None = None,
    deploy: bool = False,
    helper_url: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    source_available = source.is_dir()
    fallback_available = bool(fallback_root and fallback_root.is_dir())
    if not source_available and not fallback_available:
        raise RuntimeError(f"SMB 素材目录与本地镜像均不可达：{source}")
    generated = (now or dt.datetime.now(dt.timezone.utc)).isoformat().replace("+00:00", "Z")
    revision = urllib.parse.quote(generated, safe="")
    entries_by_id: dict[str, dict[str, object]] = {}
    previous_entries = previous.get("entries", []) if isinstance(previous, dict) else []
    labels = {
        str(entry.get("id")): entry
        for entry in previous_entries
        if isinstance(entry, dict) and entry.get("id")
    }

    def add_entry(game_name: str, game: str, character: str, variant: str, meta: dict[str, object]) -> None:
        identifier = f"{game}/{character}/{variant}"
        old = labels.get(identifier, {})
        character_zh = str(meta.get("characterZh") or old.get("characterZh") or old.get("label") or character)
        variant_zh = str(meta.get("variantZh") or old.get("variantZh") or old.get("variantLabel") or ("默认" if variant == "default" else variant))
        route = "/assets/" + "/".join(urllib.parse.quote(value, safe="") for value in (game_name, character, variant))
        light_url = f"{base_url}{route}/light?v={revision}"
        dark_url = f"{base_url}{route}/dark?v={revision}"
        entries_by_id[identifier] = {
            "id": identifier,
            "game": game,
            "gameName": game_name,
            "character": character,
            "variant": variant,
            "characterZh": character_zh,
            "variantZh": variant_zh,
            "variantLabel": variant_zh,
            "label": character_zh,
            "fullLabel": character_zh if variant == "default" else f"{character_zh} · {variant_zh}",
            "light": light_url,
            "dark": dark_url,
            "thumb": light_url,
        }

    native_report = native_source_sync(helper_url) if deploy else None
    if native_report:
        source_available = True
        discovered_source: list[dict[str, object]] = []
        recognized_games = len(GAMES)
        source_counts = {game: int(native_report["gameCounts"][game]) for game in GAMES.values()}
        deployed = int(native_report["deployedCount"])
        native_source_ids = {str(identifier) for identifier in native_report["sourceIds"]}
    else:
        discovered_source, recognized_games, source_counts = source_assets(source)
        deployed = deploy_source_assets(discovered_source, fallback_root) if deploy and source_available else 0
        native_source_ids = None
    discovered_fallback = fallback_assets(fallback_root)
    fallback_available = bool(fallback_root and fallback_root.is_dir())
    for asset in discovered_fallback:
        add_entry(str(asset["gameName"]), str(asset["game"]), str(asset["character"]), str(asset["variant"]), dict(asset["meta"]))
    for asset in discovered_source:
        add_entry(str(asset["gameName"]), str(asset["game"]), str(asset["character"]), str(asset["variant"]), dict(asset["meta"]))
    entries = list(entries_by_id.values())
    game_counts = {game: sum(1 for entry in entries if entry["game"] == game) for game in GAMES.values()}
    if any(count == 0 for count in game_counts.values()):
        missing = ", ".join(game for game, count in game_counts.items() if count == 0)
        raise RuntimeError(f"完整素材目录缺少游戏分区：{missing}")
    entries.sort(key=lambda entry: (str(entry["fullLabel"]), str(entry["id"])))
    if not entries:
        raise RuntimeError("SMB 素材目录没有完整的 light.png / dark.png 皮肤对")
    if not source_available or recognized_games < len(GAMES):
        previous_ids = {
            str(entry.get("id"))
            for entry in previous_entries
            if isinstance(entry, dict) and entry.get("id")
        }
        current_ids = set(entries_by_id)
        missing = previous_ids - current_ids
        if missing:
            raise RuntimeError(f"SMB 视图不完整且本地镜像缺少 {len(missing)} 个既有素材；已保留上一版目录")
    source_kind = "smb+local" if source_available and fallback_available else ("smb" if source_available else "local-fallback")
    catalog = {"version": 1, "source": source_kind, "generated": generated, "count": len(entries), "entries": entries}
    local_ids = {asset_identifier(asset) for asset in discovered_fallback}
    source_ids = native_source_ids.intersection(local_ids) if native_source_ids is not None else {asset_identifier(asset) for asset in discovered_source}
    if native_source_ids is not None:
        source_counts = {game: sum(1 for identifier in source_ids if identifier.startswith(f"{game}/")) for game in GAMES.values()}
    missing_from_smb = local_ids - source_ids
    missing_source_games = [game for game, count in source_counts.items() if count == 0]
    partial = not source_available or bool(missing_from_smb) or bool(missing_source_games)
    status = "partial" if partial else "ready"
    if partial:
        game_names = {game: game_name for game_name, game in GAMES.items()}
        missing_labels = "、".join(game_names.get(game, game) for game in missing_source_games)
        detail = f"；缺少分区 {missing_labels}" if missing_labels else ""
        message = (
            f"SMB 当前可用 {len(source_ids)} 个，本地完整库 {len(local_ids)} 个，总目录 {len(entries)} 个"
            f"；SMB 缺少 {len(missing_from_smb)} 个既有素材{detail}，已保留本地完整库；本次部署 {deployed} 个"
        )
    else:
        message = f"SMB、本地与总目录均为 {len(entries)} 个；本次部署 {deployed} 个"
    report = {
        "status": status,
        "message": message,
        "smbCount": len(source_ids),
        "localCount": len(local_ids),
        "catalogCount": len(entries),
        "deployedCount": deployed,
        "missingFromSMB": len(missing_from_smb),
        "missingGames": missing_source_games,
        "sourceOwner": "harness-app" if native_report else "background-service",
    }
    return catalog, report


def build_catalog(
    source: pathlib.Path,
    base_url: str,
    fallback_root: pathlib.Path | None = None,
    previous: dict[str, object] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    return synchronize_catalog(source, base_url, fallback_root, previous, now, deploy=False)[0]


def normalized_state(raw: object, catalog: dict[str, object]) -> dict[str, object]:
    value = dict(raw) if isinstance(raw, dict) else {}
    entries = catalog.get("entries") if isinstance(catalog.get("entries"), list) else []
    ordered_ids = [str(entry.get("id")) for entry in entries if isinstance(entry, dict)]
    ids = set(ordered_ids)
    hidden = list(dict.fromkeys(str(identifier) for identifier in value.get("hidden", []) if str(identifier) in ids))
    hidden_set = set(hidden)
    cycle = [str(identifier) for identifier in value.get("cycle", []) if str(identifier) in ids and str(identifier) not in hidden_set]
    selected = str(value.get("selected")) if value.get("selected") is not None else None
    if selected not in ids or selected in hidden_set:
        selected = next((identifier for identifier in ordered_ids if identifier not in hidden_set), None)
    interval = int(value.get("intervalMs") or 14_400_000)
    if interval < 60_000:
        interval = 14_400_000
    return {
        "version": 1,
        "mode": "rotate" if value.get("mode") == "rotate" else "gallery",
        "selected": selected,
        "intervalMs": interval,
        "hidden": hidden,
        "cycle": cycle,
        "cursor": max(0, min(int(value.get("cursor") or 0), len(cycle))),
        "lastRotate": int(value.get("lastRotate") or 0),
        "updated": int(value.get("updated") or 0),
        "catalogGenerated": str(catalog.get("generated") or value.get("catalogGenerated") or ""),
    }


class HarnessStore:
    def __init__(self, data_root: pathlib.Path, source: pathlib.Path, fallback_root: pathlib.Path | None, base_url: str, helper_url: str | None = None):
        self.data_root = data_root
        self.source = source
        self.fallback_root = fallback_root
        self.base_url = base_url
        self.helper_url = helper_url
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.catalog_file = data_root / "catalog.json"
        self.state_file = data_root / "state.json"
        self.status_file = data_root / "refresh-status.json"
        data_root.mkdir(parents=True, exist_ok=True)
        loaded = read_json(self.catalog_file, {"version": 1, "source": "smb", "generated": "", "count": 0, "entries": []})
        self.catalog = loaded if isinstance(loaded, dict) else {"version": 1, "source": "smb", "generated": "", "count": 0, "entries": []}
        self.state = normalized_state(read_json(self.state_file, {}), self.catalog)
        self.refresh_status: dict[str, object] = {"status": "idle", "message": "尚未刷新", "updated": 0}

    def refresh(self) -> None:
        if not self.refresh_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                self.refresh_status = {"status": "running", "message": "正在读取 SMB 素材目录", "updated": int(time.time() * 1000)}
                atomic_json(self.status_file, self.refresh_status)
            next_catalog, report = synchronize_catalog(
                self.source,
                self.base_url,
                self.fallback_root,
                self.catalog,
                deploy=True,
                helper_url=self.helper_url,
            )
            with self.lock:
                self.catalog = next_catalog
                self.state = normalized_state(self.state, next_catalog)
                self.state["updated"] = int(time.time() * 1000)
                atomic_json(self.catalog_file, self.catalog)
                atomic_json(self.state_file, self.state)
                self.refresh_status = {**report, "updated": self.state["updated"]}
                atomic_json(self.status_file, self.refresh_status)
        except Exception as error:
            with self.lock:
                self.refresh_status = {"status": "failed", "message": str(error), "updated": int(time.time() * 1000)}
                atomic_json(self.status_file, self.refresh_status)
        finally:
            self.refresh_lock.release()

    def start_refresh(self) -> None:
        threading.Thread(target=self.refresh, name="harness-catalog-refresh", daemon=True).start()

    def patch_state(self, patch: object) -> dict[str, object]:
        if not isinstance(patch, dict):
            raise ValueError("state patch must be an object")
        with self.lock:
            candidate = dict(self.state)
            for key in WRITABLE:
                if key in patch:
                    candidate[key] = patch[key]
            candidate["updated"] = int(time.time() * 1000)
            self.state = normalized_state(candidate, self.catalog)
            atomic_json(self.state_file, self.state)
            return dict(self.state)

    def _advance_locked(self, now: int) -> dict[str, object]:
        self.state = normalized_state(self.state, self.catalog)
        entries = self.catalog.get("entries") if isinstance(self.catalog.get("entries"), list) else []
        hidden = set(self.state["hidden"])
        visible = [str(entry.get("id")) for entry in entries if isinstance(entry, dict) and str(entry.get("id")) not in hidden]
        if not visible:
            return dict(self.state)

        for _pass in range(2):
            cycle = self.state["cycle"]
            cursor = int(self.state["cursor"])
            if not cycle or cursor >= len(cycle):
                cycle = list(visible)
                random.shuffle(cycle)
                if len(cycle) > 1 and cycle[0] == self.state.get("selected"):
                    cycle.append(cycle.pop(0))
                cursor = 0
                self.state["cycle"] = cycle
            while cursor < len(cycle):
                selected = cycle[cursor]
                cursor += 1
                self.state["cursor"] = cursor
                if len(visible) > 1 and selected == self.state.get("selected"):
                    continue
                self.state["selected"] = selected
                self.state["lastRotate"] = now
                self.state["updated"] = now
                atomic_json(self.state_file, self.state)
                return dict(self.state)
        return dict(self.state)

    def next_state(self, now: int | None = None) -> dict[str, object]:
        with self.lock:
            return self._advance_locked(now if now is not None else int(time.time() * 1000))

    def rotate_state(self, force: bool = False, now: int | None = None) -> dict[str, object]:
        timestamp = now if now is not None else int(time.time() * 1000)
        with self.lock:
            self.state = normalized_state(self.state, self.catalog)
            if self.state["mode"] != "rotate":
                return dict(self.state)
            if not force and timestamp - int(self.state["lastRotate"]) < int(self.state["intervalMs"]):
                return dict(self.state)
            return self._advance_locked(timestamp)

    def assets(self, route: str) -> list[pathlib.Path]:
        parts = route.split("/")
        if len(parts) != 6 or parts[1] != "assets" or parts[5] not in {"light", "dark"}:
            return []
        game_name, character, variant = (urllib.parse.unquote(value) for value in parts[2:5])
        if game_name not in GAMES or any(not value or value in {".", ".."} or "/" in value or "\\" in value for value in (character, variant)):
            return []
        # LaunchAgents do not inherit a GUI application's macOS Network Volumes
        # grant. Prefer the durable local master, then use SMB when the process is
        # allowed to read it. This keeps the catalogue usable during TCC changes.
        game = GAMES[game_name]
        local = self.fallback_root / game / character / variant / f"{parts[5]}.png" if self.fallback_root else None
        smb = self.source / game_name / character / "skins" / variant / f"{parts[5]}.png"
        return [candidate for candidate in (local, smb) if candidate and candidate.is_file()]


class Handler(BaseHTTPRequestHandler):
    server: "HarnessServer"

    def _trusted(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def _origin_headers(self) -> dict[str, str]:
        origin = self.headers.get("Origin", "")
        parsed = urllib.parse.urlparse(origin)
        if not origin or origin == "null":
            return {}
        if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
            return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        raise PermissionError("untrusted origin")

    def send_bytes(self, status: int, body: bytes = b"", content_type: str = "application/octet-stream", headers: dict[str, str] | None = None) -> None:
        try:
            origin_headers = self._origin_headers()
        except PermissionError:
            status, body = HTTPStatus.FORBIDDEN, b""
            origin_headers = {}
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in {**origin_headers, **(headers or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

    def send_json(self, value: object, status: int = HTTPStatus.OK) -> None:
        self.send_bytes(status, json.dumps(value, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def do_OPTIONS(self) -> None:
        self.send_bytes(HTTPStatus.NO_CONTENT, headers={"Access-Control-Allow-Methods": "GET, HEAD, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"})

    def do_GET(self) -> None:
        if not self._trusted():
            self.send_bytes(HTTPStatus.BAD_REQUEST)
            return
        route = urllib.parse.urlsplit(self.path).path
        store = self.server.store
        with store.lock:
            if route == "/catalog.json":
                self.send_json(store.catalog)
                return
            if route == "/state.json":
                self.send_json(store.state)
                return
            if route == "/refresh-status.json":
                self.send_json(store.refresh_status)
                return
        for asset in store.assets(route):
            try:
                body = asset.read_bytes()
            except OSError:
                continue
            self.send_bytes(HTTPStatus.OK, body, "image/png", {"Cache-Control": "public, max-age=31536000, immutable"})
            return
        web_files = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
        if route in web_files:
            file = self.server.web_root / web_files[route]
            if file.is_file():
                content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                self.send_bytes(HTTPStatus.OK, file.read_bytes(), content_type, {"Cache-Control": "no-store"})
                return
        self.send_bytes(HTTPStatus.NOT_FOUND)

    do_HEAD = do_GET

    def do_POST(self) -> None:
        if not self._trusted():
            self.send_bytes(HTTPStatus.BAD_REQUEST)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY:
            self.send_bytes(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        route = urllib.parse.urlsplit(self.path).path
        if route == "/api/catalog/refresh":
            self.server.store.start_refresh()
            self.send_json({"status": "accepted"}, HTTPStatus.ACCEPTED)
            return
        if route == "/api/next":
            self.send_json(self.server.store.next_state())
            return
        if route in {"/api/state", "/__state"}:
            try:
                patch = json.loads(self.rfile.read(length).decode("utf-8"))
                state = self.server.store.patch_state(patch)
                if isinstance(patch, dict) and patch.get("mode") == "rotate":
                    state = self.server.store.rotate_state(force=True)
            except (ValueError, UnicodeError):
                self.send_bytes(HTTPStatus.BAD_REQUEST)
                return
            if route == "/__state":
                self.send_bytes(HTTPStatus.NO_CONTENT)
            else:
                self.send_json(state)
            return
        self.send_bytes(HTTPStatus.NOT_FOUND)

    def log_message(self, _format: str, *args: object) -> None:
        return


class HarnessServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: HarnessStore, web_root: pathlib.Path):
        self.store = store
        self.web_root = web_root
        super().__init__(address, Handler)


def recurring_refresh(store: HarnessStore, interval: int) -> None:
    while True:
        time.sleep(interval)
        store.start_refresh()


def recurring_rotation(store: HarnessStore) -> None:
    while True:
        time.sleep(60)
        store.rotate_state()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--web-root", type=pathlib.Path, required=True)
    parser.add_argument("--fallback-root", type=pathlib.Path)
    parser.add_argument("--port", type=int, default=3099)
    parser.add_argument("--native-helper-url")
    parser.add_argument("--refresh-seconds", type=int, default=900)
    args = parser.parse_args()
    base_url = f"http://127.0.0.1:{args.port}"
    fallback_root = args.fallback_root.resolve() if args.fallback_root else None
    helper_url = args.native_helper_url or f"http://127.0.0.1:{args.port + 1}/api/source-sync"
    store = HarnessStore(args.root.resolve(), args.source.resolve(), fallback_root, base_url, helper_url)
    store.start_refresh()
    threading.Thread(target=recurring_rotation, args=(store,), name="harness-rotation-scheduler", daemon=True).start()
    if args.refresh_seconds > 0:
        threading.Thread(target=recurring_refresh, args=(store, max(60, args.refresh_seconds)), name="harness-refresh-scheduler", daemon=True).start()
    with HarnessServer(("127.0.0.1", args.port), store, args.web_root.resolve()) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
