"""每轮读取 Stock_Skill Registry 与各 Skill 的 runtime/params.json：校验版本与 hash，从 GitHub 带 ETag 拉取，
校验 schema 通过才生效，否则退回 Last-Known-Good（LKG）并记 finding。

边界（写死）：
- 只拉数据：REGISTRY.json 与 <skill>/runtime/params.json 这两类 JSON；不拉、不导入、不执行任何代码；
- 拉下来的内容先按各分支自己的 validate_params 做 schema 校验，通过才写入 LKG 与本轮的 active 目录；
- 优先级：远端（校验通过）> LKG > 本地仓库文件（校验通过）> 分支内置默认（源码里的 DEFAULT_PARAMS）；
- 网络失败 / 非 JSON / 超过 1 MB / 校验失败 -> 用 LKG，并把原因写进 findings（不吞、不静默）；
- 校验里含「只许收紧、不许放宽」：各分支 validate_params 会核对关键门槛不低于仓库内默认值；
- 参数内容 sha256 变了而 params_version 没变 -> 改动没走版本管理，拒绝采纳、继续用 LKG，并记 PARAMS_CONTENT_CHANGED_WITHOUT_VERSION_BUMP；
- 每轮输出每个 Skill 的 registry 版本、params_version、params 内容 sha256、来源（REMOTE/LKG/LOCAL/BUILTIN），
  写进证据快照，中枢和页面能看到「这一轮用的是哪一版参数」。
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

RAW_BASE = "https://raw.githubusercontent.com/LinzeColin/MetaDatabase"
DEFAULT_REF = "main"
STOCK_SKILL_REMOTE_PREFIX = "Signal-Lattice/Stock_Skill"
MAX_BODY_BYTES = 1_000_000
FETCH_TIMEOUT_SECONDS = 20.0
USER_AGENT = "SignalLattice params-sync (read-only data fetch)"

SOURCE_REMOTE = "REMOTE"
SOURCE_LKG = "LKG"
SOURCE_LOCAL = "LOCAL"
SOURCE_BUILTIN = "BUILTIN"


class RegistryError(RuntimeError):
    """Registry 读不了或不合法：这一轮链路不完整，调用方应报 SYSTEM_BLOCKED。"""


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchResult:
    status: int                      # 200 | 304
    body: Optional[bytes]
    etag: Optional[str]


Fetcher = Callable[[str, Optional[str]], FetchResult]


def http_fetcher(url: str, etag: Optional[str], timeout: float = FETCH_TIMEOUT_SECONDS,
                 opener: Optional[Callable] = None) -> FetchResult:
    """默认下载器：带 If-None-Match；304 返回 (304, None)；其他失败抛 FetchError。只允许 raw.githubusercontent.com。"""
    if not url.startswith(RAW_BASE + "/"):
        raise FetchError("refusing to fetch outside %s: %s" % (RAW_BASE, url))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **({"If-None-Match": etag} if etag else {})})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise FetchError("body over %d bytes: %s" % (MAX_BODY_BYTES, url))
            return FetchResult(200, body, response.headers.get("ETag"))
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return FetchResult(304, None, etag)
        raise FetchError("HTTP %d for %s" % (exc.code, url)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError("%s for %s" % (type(exc).__name__, url)) from exc


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_version(text: Any) -> Optional[Tuple[int, ...]]:
    if not isinstance(text, str):
        return None
    try:
        parts = tuple(int(p) for p in text.split("."))
    except ValueError:
        return None
    return parts if parts and all(p >= 0 for p in parts) else None


@dataclass(frozen=True)
class ParamsSpec:
    """一个 Skill 的参数合同：registry id、参数校验器（None = 该 Skill 没有可外置的参数）。"""
    skill_id: str
    validator: Optional[Callable[[Any], Any]]


def default_specs() -> Dict[str, ParamsSpec]:
    from .branches import bottleneck, commercial, event_atlas, foresight
    return {
        "bottleneck-serenity-skill": ParamsSpec("bottleneck-serenity-skill", bottleneck.validate_params),
        "stock-commercial-opportunities": ParamsSpec("stock-commercial-opportunities", commercial.validate_params),
        "equity-event-atlas": ParamsSpec("equity-event-atlas", event_atlas.validate_params),
        "equity-foresight-signal": ParamsSpec("equity-foresight-signal", foresight.validate_params),
        "global-equity-lead-lag-atlas": ParamsSpec("global-equity-lead-lag-atlas", None),
    }


@dataclass
class SkillParams:
    skill_id: str
    project_dir: str                       # 例：bottleneck-serenity-skill（registry 的 canonical_project_path 最后一段）
    registry_version: str
    registry_current: bool
    params_version: Optional[str]
    params_sha256: Optional[str]
    source: str
    active_path: Optional[str]             # 本轮分支读取的参数文件（校验过的字节）；BUILTIN / 无参数 Skill 为 None
    findings: List[dict] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.registry_current

    def to_dict(self) -> dict:
        return {"skill_id": self.skill_id, "project_dir": self.project_dir, "registry_version": self.registry_version,
                "registry_current": self.registry_current, "params_version": self.params_version,
                "params_sha256": self.params_sha256, "source": self.source, "active_path": self.active_path,
                "findings": self.findings}


@dataclass
class Resolution:
    ref: str
    registry_sha256: str
    registry_source: str
    registry_updated_at: Optional[str]
    skills: Dict[str, SkillParams]
    findings: List[dict]

    def active_skills(self) -> List[str]:
        return [sid for sid, s in self.skills.items() if s.registry_current]

    def to_dict(self) -> dict:
        return {"ref": self.ref, "registry_sha256": self.registry_sha256, "registry_source": self.registry_source,
                "registry_updated_at": self.registry_updated_at,
                "skills": {k: v.to_dict() for k, v in self.skills.items()}, "findings": self.findings}


def validate_registry(payload: Any) -> None:
    """只验数据形状（来源/版本/current），不校验 zip 与 manifest——那是仓库 CI 的事，运行期不下载发布包。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("skills"), list) or not payload["skills"]:
        raise ValueError("registry.skills 必须是非空数组")
    seen = set()
    for skill in payload["skills"]:
        if not isinstance(skill, dict):
            raise ValueError("registry skill 必须是对象")
        for key in ("id", "latest_version", "canonical_project_path"):
            if not isinstance(skill.get(key), str) or not skill[key]:
                raise ValueError("registry skill 缺 %s" % key)
        if not isinstance(skill.get("current"), bool):
            raise ValueError("registry skill %s 的 current 必须是布尔" % skill["id"])
        if parse_version(skill["latest_version"]) is None:
            raise ValueError("registry skill %s 的版本不是数字点分：%r" % (skill["id"], skill["latest_version"]))
        if not skill["canonical_project_path"].startswith(STOCK_SKILL_REMOTE_PREFIX + "/"):
            raise ValueError("registry skill %s 不在唯一规范路径 %s 下" % (skill["id"], STOCK_SKILL_REMOTE_PREFIX))
        if skill["id"] in seen:
            raise ValueError("registry skill id 重复：%s" % skill["id"])
        seen.add(skill["id"])


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp%d" % os.getpid())
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _finding(code: str, detail: str, action: str, skill: Optional[str] = None) -> dict:
    item = {"code": code, "detail": detail, "action": action}
    if skill:
        item["skill"] = skill
    return item


class ParamsResolver:
    def __init__(self, project_root: Path, state_dir: Path, *, ref: str = DEFAULT_REF,
                 fetcher: Optional[Fetcher] = http_fetcher, specs: Optional[Mapping[str, ParamsSpec]] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        """fetcher=None：不联网（只用 LKG/本地）。project_root：Signal-Lattice 目录。state_dir：LKG 与 active 参数的落盘处。"""
        self.project_root = Path(project_root)
        self.state_dir = Path(state_dir)
        self.ref = ref
        self.fetcher = fetcher
        self.specs = dict(specs) if specs is not None else default_specs()
        self.now = now

    # ---- 路径 -------------------------------------------------------------
    def remote_url(self, project_dir: str, name: str) -> str:
        return "%s/%s/%s/%s/%s" % (RAW_BASE, self.ref, STOCK_SKILL_REMOTE_PREFIX, project_dir, name) if project_dir \
            else "%s/%s/%s/%s" % (RAW_BASE, self.ref, STOCK_SKILL_REMOTE_PREFIX, name)

    def local_stock_dir(self) -> Path:
        return self.project_root / "Stock_Skill"

    def _remote_cache(self, key: str) -> Tuple[Path, Path]:
        base = self.state_dir / "remote-cache"
        return base / (key + ".body"), base / (key + ".etag")

    def _lkg(self, skill_id: str) -> Tuple[Path, Path]:
        base = self.state_dir / "lkg"
        return base / (skill_id + ".json"), base / (skill_id + ".meta.json")

    def _active(self, skill_id: str) -> Path:
        return self.state_dir / "active" / (skill_id + ".json")

    # ---- 带 ETag 的拉取 ----------------------------------------------------
    def _fetch(self, key: str, url: str) -> Tuple[Optional[bytes], Optional[str]]:
        """返回 (字节, 错误)。304 用上次缓存的字节；任何失败返回 (None, 原因)。"""
        if self.fetcher is None:
            return None, "NETWORK_DISABLED"
        body_path, etag_path = self._remote_cache(key)
        etag = etag_path.read_text("utf-8").strip() if etag_path.is_file() and body_path.is_file() else None
        try:
            result = self.fetcher(url, etag)
        except FetchError as exc:
            return None, str(exc)
        except Exception as exc:                      # 下载器自己的意外错误也只降级，不让整轮崩
            return None, "%s: %s" % (type(exc).__name__, exc)
        if result.status == 304:
            if not body_path.is_file():
                return None, "HTTP 304 but no cached body"
            return body_path.read_bytes(), None
        if result.status != 200 or result.body is None:
            return None, "HTTP %s" % result.status
        if len(result.body) > MAX_BODY_BYTES:
            return None, "body over %d bytes" % MAX_BODY_BYTES
        _write_atomic(body_path, result.body)
        if result.etag:
            _write_atomic(etag_path, result.etag.encode("utf-8"))
        elif etag_path.is_file():
            etag_path.unlink()
        return result.body, None

    # ---- Registry -----------------------------------------------------------
    def read_registry(self) -> Tuple[dict, bytes, str, List[dict]]:
        findings: List[dict] = []
        local_path = self.local_stock_dir() / "REGISTRY.json"
        local_bytes = local_path.read_bytes() if local_path.is_file() else None
        local: Optional[dict] = None
        if local_bytes is not None:
            try:
                local = json.loads(local_bytes.decode("utf-8"))
                validate_registry(local)
            except (ValueError, UnicodeDecodeError) as exc:
                findings.append(_finding("LOCAL_REGISTRY_INVALID", str(exc), "IGNORED"))
                local = None
        remote_bytes, error = self._fetch("REGISTRY", self.remote_url("", "REGISTRY.json"))
        if remote_bytes is not None:
            try:
                remote = json.loads(remote_bytes.decode("utf-8"))
                validate_registry(remote)
                if local is not None:
                    differing = sorted(s["id"] for s in remote["skills"]
                                       if not any(l["id"] == s["id"] and l["latest_version"] == s["latest_version"] and l["current"] == s["current"]
                                                  for l in local["skills"]))
                    if differing:
                        findings.append(_finding("REGISTRY_REMOTE_DIFFERS_FROM_LOCAL", ",".join(differing), "USING_REMOTE"))
                return remote, remote_bytes, SOURCE_REMOTE, findings
            except (ValueError, UnicodeDecodeError) as exc:
                findings.append(_finding("REMOTE_REGISTRY_INVALID", str(exc), "USING_LOCAL_REGISTRY"))
        elif error != "NETWORK_DISABLED":
            findings.append(_finding("REMOTE_REGISTRY_UNAVAILABLE", error or "", "USING_LOCAL_REGISTRY"))
        if local is None or local_bytes is None:
            raise RegistryError("Registry 远端与本地都不可用/不合法：链路不完整")
        return local, local_bytes, SOURCE_LOCAL, findings

    # ---- 参数 ---------------------------------------------------------------
    @staticmethod
    def _load_valid(payload: bytes, validator: Optional[Callable[[Any], Any]]) -> Tuple[Optional[dict], Optional[str]]:
        try:
            parsed = json.loads(payload.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("params 必须是 JSON 对象")
            if validator is not None:
                validator(parsed)
            if not isinstance(parsed.get("params_version"), str):
                raise ValueError("params_version 缺失或不是字符串")
            return parsed, None
        except (ValueError, UnicodeDecodeError, TypeError, KeyError) as exc:
            return None, "%s: %s" % (type(exc).__name__, exc)

    def _read_lkg(self, spec: ParamsSpec) -> Optional[Tuple[bytes, dict]]:
        body_path, _ = self._lkg(spec.skill_id)
        if not body_path.is_file():
            return None
        payload = body_path.read_bytes()
        parsed, error = self._load_valid(payload, spec.validator)
        return (payload, parsed) if parsed is not None else None      # LKG 自己坏了就当没有

    def _save_lkg(self, spec: ParamsSpec, payload: bytes, parsed: dict, source: str) -> None:
        body_path, meta_path = self._lkg(spec.skill_id)
        _write_atomic(body_path, payload)
        _write_atomic(meta_path, json.dumps({"params_version": parsed["params_version"], "sha256": sha256_hex(payload),
                                             "adopted_at": self.now().isoformat(), "source": source}).encode("utf-8"))

    def resolve_skill(self, skill: Mapping[str, Any]) -> SkillParams:
        skill_id = skill["id"]
        project_dir = skill["canonical_project_path"].rsplit("/", 1)[-1]
        spec = self.specs.get(skill_id)
        result = SkillParams(skill_id, project_dir, skill["latest_version"], bool(skill["current"]), None, None, SOURCE_BUILTIN, None, [])
        if spec is None:
            result.findings.append(_finding("SKILL_NOT_IMPLEMENTED_IN_RUNTIME", "registry 有此 Skill，本仓运行时没有对应分支", "NOT_DISPATCHED", skill_id))
            result.registry_current = False       # 没有实现就不能算 Active 分发对象；也不假装参与
            return result
        if spec.validator is None:                # 没有外置参数的 Skill（全球联动）：只记 registry 版本
            result.source = SOURCE_LOCAL
            return result

        local_path = self.local_stock_dir() / project_dir / "runtime" / "params.json"
        local_payload = local_path.read_bytes() if local_path.is_file() else None
        local, local_error = (self._load_valid(local_payload, spec.validator) if local_payload is not None
                              else (None, "PARAMS_FILE_MISSING"))
        lkg = self._read_lkg(spec)
        chosen: Optional[Tuple[bytes, dict, str]] = None

        remote_payload, fetch_error = self._fetch("params-" + skill_id, self.remote_url(project_dir, "runtime/params.json"))
        if remote_payload is not None:
            remote, remote_error = self._load_valid(remote_payload, spec.validator)
            # 「之前」= LKG；首次运行没有 LKG 时以本地仓库文件为参照
            reference_payload, reference = (lkg[0], lkg[1]) if lkg else (local_payload, local)
            if remote is None:
                result.findings.append(_finding("REMOTE_PARAMS_INVALID", remote_error or "", "KEEPING_LKG", skill_id))
            elif (reference is not None and remote["params_version"] == reference["params_version"]
                  and sha256_hex(remote_payload) != sha256_hex(reference_payload)):
                # 内容变了、版本号没变：改动没有走版本管理，不采纳；继续用 LKG（没有 LKG 用本地仓库文件）
                result.findings.append(_finding("PARAMS_CONTENT_CHANGED_WITHOUT_VERSION_BUMP",
                                                "%s：远端内容 sha256 %s 与已采纳的 %s 不同，但版本号仍是 %s" % (
                                                    skill_id, sha256_hex(remote_payload)[:12], sha256_hex(reference_payload)[:12],
                                                    reference["params_version"]),
                                                "REJECTED_KEEPING_LKG" if lkg else "REJECTED_KEEPING_LOCAL", skill_id))
            else:
                chosen = (remote_payload, remote, SOURCE_REMOTE)
        elif fetch_error != "NETWORK_DISABLED":
            result.findings.append(_finding("REMOTE_PARAMS_UNAVAILABLE", fetch_error or "", "KEEPING_LKG", skill_id))

        if chosen is None:
            if lkg is not None:
                chosen = (lkg[0], lkg[1], SOURCE_LKG)
                # 本地仓库带来了更新的合格参数（随发布升级）：采纳，并成为新的 LKG
                if local is not None and (parse_version(local["params_version"]) or ()) > (parse_version(lkg[1]["params_version"]) or ()):
                    chosen = (local_payload, local, SOURCE_LOCAL)
            elif local is not None:
                chosen = (local_payload, local, SOURCE_LOCAL)         # 首次运行：本地合格文件成为 LKG
            else:
                result.findings.append(_finding("NO_VALID_PARAMS", "远端/LKG/本地都不可用：%s" % (local_error or ""),
                                                "USING_BUILTIN_DEFAULTS", skill_id))
                return result

        payload, parsed, source = chosen
        # 「之前」= LKG；首次运行没有 LKG 时以本地仓库文件为参照（远端版本与它不同也算版本变化）
        reference_payload, reference = (lkg[0], lkg[1]) if lkg else (local_payload, local)
        previous = reference["params_version"] if reference else None
        digest = sha256_hex(payload)
        if source in (SOURCE_REMOTE, SOURCE_LOCAL):
            reference_sha = sha256_hex(reference_payload) if reference is not None else None
            if digest != reference_sha or lkg is None:
                if previous is not None and previous != parsed["params_version"]:
                    result.findings.append(_finding("PARAMS_UPDATED", "%s -> %s（%s）" % (previous, parsed["params_version"], source),
                                                    "NEW_PARAMS_ACTIVE", skill_id))
            if lkg is None or digest != sha256_hex(lkg[0]):
                self._save_lkg(spec, payload, parsed, source)
        active = self._active(skill_id)
        _write_atomic(active, payload)
        result.params_version, result.params_sha256, result.source, result.active_path = parsed["params_version"], digest, source, str(active)
        return result

    def resolve(self) -> Resolution:
        registry, registry_bytes, registry_source, findings = self.read_registry()
        skills: Dict[str, SkillParams] = {}
        for skill in registry["skills"]:
            skills[skill["id"]] = self.resolve_skill(skill)
        return Resolution(self.ref, sha256_hex(registry_bytes), registry_source, registry.get("updated_at"), skills, findings)
