"""无人值守层测试用的离线假数据源与假 GitHub。"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app.headless import sources as src

CST = ZoneInfo("Asia/Shanghai")
LAST_DAY = date(2026, 9, 29)


def business_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(days)


def nav_series(seed: int, end: date = LAST_DAY, count: int = 900) -> list[tuple[date, float]]:
    return [(day, round(1.0 + 0.0004 * i + 0.05 * math.sin((i + seed) / 17.0), 4)) for i, day in enumerate(business_days(end, count))]


def epoch_ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=CST).astimezone(timezone.utc).timestamp() * 1000)


def pingzhong_text(seed: int) -> bytes:
    series = [{"x": epoch_ms(d), "y": v, "equityReturn": 0, "unitMoney": ""} for d, v in nav_series(seed)]
    return f'var fS_name = "测试基金";\nvar Data_netWorthTrend = {json.dumps(series)};\nvar Data_ACWorthTrend = [];'.encode()


class FakeClient:
    """按 URL 模式返回固定数据；fail 里列出的关键字命中时抛 SourceError。"""

    def __init__(self, fail: tuple[str, ...] = ()) -> None:
        self.fail = fail
        self.urls: list[str] = []
        self.request_count = 0

    def get(self, url: str, headers=None) -> bytes:
        self.urls.append(url)
        self.request_count += 1
        for key in self.fail:
            if key in url:
                raise src.SourceError(f"fake failure for {key}")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "pingzhongdata" in url:
            code = parsed.path.rsplit("/", 1)[-1].split(".")[0]
            return pingzhong_text(int(code[-3:]) if code[-3:].isdigit() else 1)
        if "lsjz" in url:
            code = query["fundCode"][0]
            series = nav_series(int(code[-3:]))
            start = query.get("startDate", [None])[0]
            rows = [
                {"FSRQ": d.isoformat(), "DWJZ": str(v), "SGZT": "开放申购", "SHZT": "开放赎回"}
                for d, v in reversed(series)
                if not start or d.isoformat() >= start
            ]
            size = int(query["pageSize"][0])
            page = int(query["pageIndex"][0])
            return json.dumps({"ErrCode": 0, "TotalCount": len(rows), "Data": {"LSJZList": rows[(page - 1) * size : page * size]}}).encode()
        if "yunhq.sse.com.cn" in url:
            kline = [[int(d.strftime("%Y%m%d")), 3000.0 + i] for i, d in enumerate(business_days(date(2026, 9, 30), 900))]
            return json.dumps({"code": "000001", "kline": kline}).encode()
        if "fredgraph" in url:
            rows = "\n".join(f"{d.isoformat()},{5000 + i}" for i, d in enumerate(business_days(LAST_DAY, 700)))
            return f"observation_date,SP500\n{rows}\n".encode()
        raise src.SourceError(f"unexpected url {url}")


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._raw = json.dumps(payload).encode() if payload is not None else b""
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


class FakeGitHub:
    """最小的 GitHub Release API 假实现，记录所有请求。"""

    def __init__(self, private: bool = True) -> None:
        self.private = private
        self.calls: list[tuple[str, str]] = []
        self.releases: dict[int, dict] = {}
        self.assets: dict[int, dict[str, bytes]] = {}
        self.bodies: list[bytes | None] = []
        self._next = 100

    def __call__(self, request, timeout=None):
        method, url = request.get_method(), request.full_url
        self.calls.append((method, url))
        path = urlparse(url).path
        if method == "GET" and path.count("/") == 3:  # /repos/o/r
            return FakeResponse({"private": self.private})
        if method == "POST" and path.endswith("/releases"):
            self._next += 1
            data = json.loads(request.data.decode())
            self.releases[self._next] = {"id": self._next, "tag_name": data["tag_name"], "html_url": f"https://example.invalid/r/{self._next}", "upload_url": "", "assets": [], "draft": data["draft"], "body": data["body"]}
            self.assets[self._next] = {}
            return FakeResponse(self.releases[self._next])
        parts = path.split("/")
        if method == "GET" and "releases" in parts and parts[-1].isdigit():
            rid = int(parts[-1])
            release = dict(self.releases[rid])
            release["assets"] = [{"name": n, "id": rid * 1000 + i} for i, n in enumerate(self.assets[rid])]
            return FakeResponse(release)
        if method == "POST" and path.endswith("/assets"):
            rid = int(parts[-2])
            name = dict(x.split("=", 1) for x in urlparse(url).query.split("&"))["name"]
            self.assets[rid][name] = request.data
            return FakeResponse({"id": rid * 1000 + len(self.assets[rid]), "name": name})
        if method == "DELETE":
            rid_asset = int(parts[-1])
            rid = rid_asset // 1000
            for name in list(self.assets[rid]):
                pass
            return FakeResponse(None)
        if method == "PATCH":
            rid = int(parts[-1])
            self.releases[rid]["body"] = json.loads(request.data.decode())["body"]
            return FakeResponse(self.releases[rid])
        raise AssertionError(f"unhandled {method} {url}")
