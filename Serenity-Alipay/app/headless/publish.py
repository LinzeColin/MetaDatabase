"""把报告写成私有仓的 GitHub Release 资产（草稿 Release，每个北京日一个）。

- 只写 Release（草稿，不建 git 标签、不动任何分支文件）；tag 固定前缀 serenity-report-。
- 令牌只从 systemd LoadCredential 挂进来的只读文件读取（$CREDENTIALS_DIRECTORY/github_token
  或 SERENITY_GITHUB_TOKEN_FILE），不打印、不落盘、不写进异常信息。
- 发布前核对目标仓 private=true，不是私有仓一律拒绝（报告不该出现在公开仓）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_REPO = "LinzeColin/Private-Database"
TAG_PREFIX = "serenity-report-"
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


class PublishError(RuntimeError):
    pass


def read_token(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else dict(os.environ)
    candidates: list[Path] = []
    if env.get("SERENITY_GITHUB_TOKEN_FILE"):
        candidates.append(Path(env["SERENITY_GITHUB_TOKEN_FILE"]))
    if env.get("CREDENTIALS_DIRECTORY"):
        candidates.append(Path(env["CREDENTIALS_DIRECTORY"]) / "github_token")
    for path in candidates:
        if path.is_file():
            token = path.read_text(encoding="utf-8").strip()
            if token:
                return token
    raise PublishError("没有可用的 GitHub 令牌文件（需要 systemd LoadCredential=github_token 或 SERENITY_GITHUB_TOKEN_FILE）")


@dataclass
class Release:
    id: int
    tag: str
    html_url: str
    upload_url: str
    assets: dict[str, int]


class ReleasePublisher:
    def __init__(
        self,
        token: str,
        *,
        repo: str = DEFAULT_REPO,
        index_path: Path | None = None,
        opener=urlopen,
        sleep=time.sleep,
        retries: int = 3,
        timeout: float = 60.0,
    ) -> None:
        self._token = token
        self.repo = repo
        self.index_path = index_path
        self._opener = opener
        self._sleep = sleep
        self.retries = retries
        self.timeout = timeout

    # ---- 低层请求
    def _request(self, method: str, url: str, *, data: bytes | None = None, content_type: str | None = None) -> object:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SerenityDailyAnalysis/1.0",
        }
        if content_type:
            headers["Content-Type"] = content_type
        last: str = ""
        for attempt in range(1, self.retries + 1):
            try:
                with self._opener(Request(url, data=data, headers=headers, method=method), timeout=self.timeout) as response:  # noqa: S310 - 固定 GitHub 端点
                    raw = response.read()
                    return json.loads(raw.decode("utf-8")) if raw else {}
            except HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code < 500 and exc.code != 429:
                    raise PublishError(f"GitHub {method} {url.split('?')[0]} 失败：{last}") from None
            except (URLError, TimeoutError, OSError) as exc:
                last = exc.__class__.__name__
            if attempt < self.retries:
                self._sleep(2.0 * attempt)
        raise PublishError(f"GitHub {method} {url.split('?')[0]} 失败：{last}")

    def _json(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        result = self._request(method, f"{API}{path}", data=payload, content_type="application/json" if payload else None)
        return result if isinstance(result, dict) else {}

    # ---- 索引：日期 -> release id（草稿 Release 按 tag 查不到，所以自己记）
    def _load_index(self) -> dict[str, int]:
        if self.index_path and self.index_path.exists():
            try:
                return {str(k): int(v) for k, v in json.loads(self.index_path.read_text(encoding="utf-8")).items()}
            except (ValueError, json.JSONDecodeError):
                return {}
        return {}

    def _save_index(self, index: dict[str, int]) -> None:
        if self.index_path:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

    def assert_private_repo(self) -> None:
        info = self._json("GET", f"/repos/{self.repo}")
        if info.get("private") is not True:
            raise PublishError(f"{self.repo} 不是私有仓，拒绝发布报告")

    @staticmethod
    def _to_release(data: dict[str, object]) -> Release:
        assets = {str(a["name"]): int(a["id"]) for a in data.get("assets", [])}  # type: ignore[union-attr]
        return Release(int(data["id"]), str(data["tag_name"]), str(data.get("html_url", "")), str(data.get("upload_url", "")), assets)

    def ensure_release(self, day: str, name: str, body: str) -> Release:
        tag = f"{TAG_PREFIX}{day}"
        index = self._load_index()
        if day in index:
            try:
                return self._to_release(self._json("GET", f"/repos/{self.repo}/releases/{index[day]}"))
            except PublishError:
                index.pop(day, None)  # 记录的 Release 没了（被人删掉）：重建
        created = self._json(
            "POST",
            f"/repos/{self.repo}/releases",
            {"tag_name": tag, "name": name, "body": body, "draft": True, "prerelease": False, "make_latest": "false"},
        )
        release = self._to_release(created)
        index[day] = release.id
        self._save_index(index)
        return release

    def upload_asset(self, release: Release, name: str, data: bytes, content_type: str) -> None:
        if name in release.assets:  # 同名资产是本服务自己上传的旧版本：先换掉，保证重发幂等
            self._request("DELETE", f"{API}/repos/{self.repo}/releases/assets/{release.assets[name]}")
        result = self._request("POST", f"{UPLOADS}/repos/{self.repo}/releases/{release.id}/assets?name={quote(name)}", data=data, content_type=content_type)
        if isinstance(result, dict) and result.get("id"):
            release.assets[name] = int(result["id"])

    def update_body(self, release: Release, body: str) -> None:
        self._json("PATCH", f"/repos/{self.repo}/releases/{release.id}", {"body": body})
