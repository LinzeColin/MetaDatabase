#!/usr/bin/env python3
"""Loopback HarnessUI catalogue, state, gallery, and SMB asset service."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import pathlib
import threading
import time
import urllib.parse
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


def build_catalog(
    source: pathlib.Path,
    base_url: str,
    fallback_root: pathlib.Path | None = None,
    previous: dict[str, object] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, object]:
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

    if fallback_root and fallback_root.is_dir():
        reverse_games = {game: game_name for game_name, game in GAMES.items()}
        for game, game_name in reverse_games.items():
            for character_root in child_directories(fallback_root / game):
                for variant_root in child_directories(character_root):
                    if (variant_root / "light.png").is_file() and (variant_root / "dark.png").is_file():
                        add_entry(game_name, game, character_root.name, variant_root.name, {})
    recognized_games = 0
    if source_available:
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
                    character = character_root.name
                    variant = variant_root.name
                    meta = read_json(variant_root / "meta.json", {})
                    if not isinstance(meta, dict):
                        meta = {}
                    add_entry(game_name, game, character, variant, meta)
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
    return {"version": 1, "source": source_kind, "generated": generated, "count": len(entries), "entries": entries}


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
    def __init__(self, data_root: pathlib.Path, source: pathlib.Path, fallback_root: pathlib.Path | None, base_url: str):
        self.data_root = data_root
        self.source = source
        self.fallback_root = fallback_root
        self.base_url = base_url
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
            next_catalog = build_catalog(self.source, self.base_url, self.fallback_root, self.catalog)
            with self.lock:
                self.catalog = next_catalog
                self.state = normalized_state(self.state, next_catalog)
                self.state["updated"] = int(time.time() * 1000)
                atomic_json(self.catalog_file, self.catalog)
                atomic_json(self.state_file, self.state)
                self.refresh_status = {"status": "ready", "message": f"已同步 {next_catalog['count']} 个变体", "updated": self.state["updated"]}
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
            self.wfile.write(body)

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
        if route in {"/api/state", "/__state"}:
            try:
                patch = json.loads(self.rfile.read(length).decode("utf-8"))
                state = self.server.store.patch_state(patch)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--web-root", type=pathlib.Path, required=True)
    parser.add_argument("--fallback-root", type=pathlib.Path)
    parser.add_argument("--port", type=int, default=3099)
    parser.add_argument("--refresh-seconds", type=int, default=900)
    args = parser.parse_args()
    base_url = f"http://127.0.0.1:{args.port}"
    fallback_root = args.fallback_root.resolve() if args.fallback_root else None
    store = HarnessStore(args.root.resolve(), args.source.resolve(), fallback_root, base_url)
    store.start_refresh()
    if args.refresh_seconds > 0:
        threading.Thread(target=recurring_refresh, args=(store, max(60, args.refresh_seconds)), name="harness-refresh-scheduler", daemon=True).start()
    with HarnessServer(("127.0.0.1", args.port), store, args.web_root.resolve()) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
