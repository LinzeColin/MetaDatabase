from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings


settings = get_settings()
MANUAL_ONLY_DOMAINS = {
    "seek.com.au",
    "www.seek.com.au",
    "linkedin.com",
    "www.linkedin.com",
    "indeed.com",
    "www.indeed.com",
    "glassdoor.com",
    "www.glassdoor.com",
}
# Server-side reads are limited to established ATS domains. Arbitrary company
# domains still remain useful as stored source links, but their JD must be pasted.
# This keeps the private server from becoming a general-purpose URL fetcher.
FETCH_ALLOWED_SUFFIXES = {
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "oraclecloud.com",
}
MAX_REDIRECTS = 4
USER_AGENT = (
    "Mozilla/5.0 (compatible; JobHuntBotOnline/0.1; "
    "+private-candidate-workflow; contact=owner)"
)


@dataclass
class JobDocument:
    url: str
    source: str
    company: str
    title: str
    location: str
    posted_date: str
    description: str
    snapshot_text: str
    fetched: bool
    manual_reason: str = ""


class JobFetchError(ValueError):
    pass


def source_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "greenhouse" in host:
        return "Greenhouse"
    if "lever.co" in host:
        return "Lever"
    if "ashbyhq.com" in host:
        return "Ashby"
    if "workday" in host or "myworkdayjobs" in host:
        return "Workday"
    if "oraclecloud" in host or "taleo" in host:
        return "Oracle / Taleo"
    if "linkedin" in host:
        return "LinkedIn"
    if "seek" in host:
        return "SEEK"
    if "indeed" in host:
        return "Indeed"
    return host or "Manual"


def _host_matches(host: str, suffixes: set[str]) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def domain_is_fetch_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return bool(host) and _host_matches(host, FETCH_ALLOWED_SUFFIXES)


def domain_requires_manual_paste(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return _host_matches(host, MANUAL_ONLY_DOMAINS) or not domain_is_fetch_allowed(url)


async def fetch_job_document(url: str) -> JobDocument:
    normalized = _validate_url(url)
    if domain_requires_manual_paste(normalized):
        host = (urlparse(normalized).hostname or "").lower()
        platform_message = (
            "该招聘平台不使用服务器自动读取。"
            if _host_matches(host, MANUAL_ONLY_DOMAINS)
            else "安全模式只自动读取已知 ATS 的公开职位页。"
        )
        return JobDocument(
            url=normalized,
            source=source_from_url(normalized),
            company="",
            title="",
            location="",
            posted_date="",
            description="",
            snapshot_text="",
            fetched=False,
            manual_reason=platform_message + "链接会保留，请复制职位正文到下方文本框。",
        )

    current_url = validate_fetch_target(normalized)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.job_fetch_timeout_seconds),
        follow_redirects=False,
        trust_env=False,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-AU,en;q=0.9,zh-CN;q=0.7",
        },
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            current_url = validate_fetch_target(current_url)
            await _assert_public_host(current_url)
            try:
                async with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise JobFetchError("岗位页面返回了无效跳转。")
                        current_url = validate_fetch_target(urljoin(current_url, location))
                        continue
                    if response.status_code >= 400:
                        raise JobFetchError(f"岗位页面无法读取（HTTP {response.status_code}）。请直接粘贴职位正文。")
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type and "application/xhtml" not in content_type:
                        raise JobFetchError("链接不是可读取的网页。请直接粘贴职位正文。")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > settings.job_fetch_max_bytes:
                            raise JobFetchError("岗位页面过大。请直接粘贴职位正文。")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    html = body.decode(encoding, errors="replace")
                    return parse_job_html(current_url, html)
            except JobFetchError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                raise JobFetchError("岗位页面暂时无法读取。请检查链接或直接粘贴职位正文。") from exc
        raise JobFetchError("岗位链接跳转次数过多。请直接粘贴职位正文。")


def parse_job_html(url: str, html: str) -> JobDocument:
    soup = BeautifulSoup(html, "html.parser")
    structured = _extract_job_posting_jsonld(soup)

    title = _string_value(structured.get("title"))
    company = _company_value(structured.get("hiringOrganization"))
    location = _location_value(structured.get("jobLocation") or structured.get("applicantLocationRequirements"))
    posted_date = _date_value(structured.get("datePosted"))
    description_html = _string_value(structured.get("description"))
    description = _html_to_text(description_html) if description_html else ""

    if not title:
        title = _meta_content(soup, "property", "og:title") or _meta_content(soup, "name", "twitter:title")
    if not title:
        heading = soup.find("h1")
        title = heading.get_text(" ", strip=True) if heading else ""

    if not company:
        company = _meta_content(soup, "property", "og:site_name")

    if not description or len(description) < 120:
        page_text = _main_page_text(soup)
        if len(page_text) > len(description):
            description = page_text

    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    title = _clean_short(title, 300)
    company = _clean_short(company, 240)
    location = _clean_short(location, 240)
    description = _clean_long(description)

    if len(description) < 120:
        raise JobFetchError("页面没有提供足够的职位正文。请直接粘贴职位描述。")

    return JobDocument(
        url=url,
        source=source_from_url(url),
        company=company,
        title=title,
        location=location,
        posted_date=posted_date,
        description=description,
        snapshot_text=description,
        fetched=True,
    )


def job_document_from_manual(
    *,
    url: str,
    company: str,
    title: str,
    location: str,
    posted_date: str,
    description: str,
) -> JobDocument:
    cleaned_description = _clean_long(description)
    if len(cleaned_description) < 120:
        raise JobFetchError("请粘贴更完整的职位描述，至少包含主要职责和任职要求。")
    normalized_url = ""
    if url.strip():
        normalized_url = _validate_url(url)
    return JobDocument(
        url=normalized_url,
        source=source_from_url(normalized_url) if normalized_url else "Manual",
        company=_clean_short(company, 240) or "Unknown company",
        title=_clean_short(title, 300) or "Unknown role",
        location=_clean_short(location, 240),
        posted_date=_date_value(posted_date),
        description=cleaned_description,
        snapshot_text=cleaned_description,
        fetched=False,
    )


def _validate_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise JobFetchError("请输入岗位链接。")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise JobFetchError("岗位链接必须是完整的 https 地址。")
    if parsed.username or parsed.password:
        raise JobFetchError("岗位链接不能包含账号或密码。")
    if parsed.port and parsed.port != 443:
        raise JobFetchError("岗位链接使用了不允许的端口。")
    return parsed.geturl()


def validate_fetch_target(url: str) -> str:
    normalized = _validate_url(url)
    if not domain_is_fetch_allowed(normalized):
        raise JobFetchError("岗位页面跳转到了未授权域名。请直接粘贴职位正文。")
    return normalized


async def _assert_public_host(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise JobFetchError("岗位链接缺少域名。")
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise JobFetchError("岗位域名无法解析。请检查链接或直接粘贴职位正文。") from exc
    if not addresses:
        raise JobFetchError("岗位域名没有可用地址。")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise JobFetchError("该链接指向非公开网络地址，不能由服务器读取。")


def _extract_job_posting_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _walk_jsonld(data):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(value).lower() == "jobposting" for value in types if value):
                return item
    return {}


def _walk_jsonld(data: Any):  # type: ignore[no-untyped-def]
    if isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if graph is not None:
            yield from _walk_jsonld(graph)
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from _walk_jsonld(value)
    elif isinstance(data, list):
        for item in data:
            yield from _walk_jsonld(item)


def _company_value(value: Any) -> str:
    if isinstance(value, dict):
        return _string_value(value.get("name"))
    return _string_value(value)


def _location_value(value: Any) -> str:
    if isinstance(value, list):
        parts = [_location_value(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        address = value.get("address", value)
        if isinstance(address, dict):
            parts = [
                _string_value(address.get("addressLocality")),
                _string_value(address.get("addressRegion")),
                _string_value(address.get("addressCountry")),
            ]
            return ", ".join(part for part in parts if part)
        return _string_value(address)
    return _string_value(value)


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _date_value(value: Any) -> str:
    text = _string_value(value).strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        return text[:80]


def _meta_content(soup: BeautifulSoup, key: str, value: str) -> str:
    tag = soup.find("meta", attrs={key: value})
    return tag.get("content", "").strip() if tag else ""


def _html_to_text(value: str) -> str:
    fragment = BeautifulSoup(unescape(value), "html.parser")
    return fragment.get_text("\n", strip=True)


def _main_page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    candidates = [
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.find("article"),
        soup.body,
    ]
    for candidate in candidates:
        if candidate:
            text = candidate.get_text("\n", strip=True)
            if len(text) >= 200:
                return text
    return soup.get_text("\n", strip=True)


def _clean_short(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()[:limit]


def _clean_long(value: str) -> str:
    text = unescape(value or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:100_000]
