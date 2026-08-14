from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import Candidate


def _normalized(value: str) -> str:
    return " ".join(value.upper().replace("-", " ").replace("_", " ").split())


def _token_matches(text: str, tokens: list[str]) -> list[str]:
    normalized = _normalized(text)
    return [token for token in tokens if _normalized(token) in normalized]


def _has_any(text: str, tokens: list[str]) -> bool:
    return bool(_token_matches(text, tokens))


def _candidate_from_row(
    row: dict[str, Any], bucket: dict[str, Any], defensive_tokens: list[str], leveraged_tokens: list[str]
) -> Candidate:
    code = str(row.get("provider_code") or row.get("code") or "").upper()
    market = str(row.get("market") or code.split(".", 1)[0]).upper()
    public_code = str(row.get("public_code") or code.split(".")[-1]).upper()
    name = str(row.get("name") or public_code)
    inverse = _has_any(f"{name} {code}", defensive_tokens)
    leveraged = _has_any(f"{name} {code}", leveraged_tokens)
    base_tier = int(bucket.get("risk_tier", 1))
    return Candidate(
        provider_code=code,
        public_code=public_code,
        name=name,
        market=market,
        currency=str(row.get("currency", "AUD" if market == "AU" else "HKD" if market == "HK" else "USD")),
        bucket_id=str(bucket["id"]),
        bucket_name=str(bucket["name"]),
        risk_tier=3 if inverse or leveraged else base_tier,
        platform_verified=bool(row.get("platform_verified", True)),
        metadata=dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {},
        inverse=inverse,
        leveraged=leveraged,
        path_dependency_verified=bool(row.get("path_dependency_verified", False)),
        liquidity_score=float(row.get("liquidity_score", 0.0) or 0.0),
        discovery_source=str(row.get("discovery_source", "platform_catalog")),
    )


def discover_candidates(catalog: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[Candidate], str, dict[str, Any]]:
    preference = {market: index for index, market in enumerate(config.get("market_preference", []))}
    max_per_bucket = max(1, min(int(config.get("max_candidates_per_bucket", 2)), 10))
    buckets = [row for row in config.get("buckets", []) if isinstance(row, dict)]
    grouped: dict[str, list[Candidate]] = defaultdict(list)
    dynamic_hits: dict[str, int] = defaultdict(int)
    fallback_hits: dict[str, int] = defaultdict(int)
    defensive_tokens = [str(x) for x in config.get("defensive_tokens", [])]
    leveraged_tokens = [str(x) for x in config.get("leveraged_tokens", [])]

    # Each platform product belongs to one best-matching bucket. This prevents
    # duplicate products from silently competing as several different assets.
    for row in catalog:
        if not isinstance(row, dict):
            continue
        code = str(row.get("provider_code") or row.get("code") or "").upper()
        if not code:
            continue
        text = f"{row.get('name', '')} {code}"
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for index, bucket in enumerate(buckets):
            matches = _token_matches(text, [str(x) for x in bucket.get("include_tokens", [])])
            if matches:
                ranked.append((max(len(_normalized(token)) for token in matches), -index, bucket))
        if not ranked:
            continue
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        bucket = ranked[0][2]
        candidate = _candidate_from_row(row, bucket, defensive_tokens, leveraged_tokens)
        grouped[candidate.bucket_id].append(candidate)
        dynamic_hits[candidate.bucket_id] += 1

    for bucket in buckets:
        bucket_id = str(bucket["id"])
        seen = {item.provider_code for item in grouped[bucket_id]}
        for row in bucket.get("fallback", []):
            if not isinstance(row, dict):
                continue
            code = str(row.get("provider_code", "")).upper()
            if not code or code in seen:
                continue
            fallback_row = {
                **row,
                "platform_verified": False,
                "discovery_source": "fallback_seed",
            }
            grouped[bucket_id].append(_candidate_from_row(fallback_row, bucket, defensive_tokens, leveraged_tokens))
            fallback_hits[bucket_id] += 1

    selected: list[Candidate] = []
    for bucket in buckets:
        bucket_id = str(bucket["id"])
        rows = grouped.get(bucket_id, [])
        rows.sort(key=lambda item: (
            0 if item.platform_verified else 1,
            preference.get(item.market, 99),
            -item.liquidity_score,
            item.provider_code,
        ))
        selected.extend(rows[:max_per_bucket])

    dynamic_buckets = sum(1 for bucket in buckets if dynamic_hits.get(str(bucket["id"]), 0) > 0)
    total_buckets = len(buckets)
    if dynamic_buckets == total_buckets and total_buckets:
        coverage = "平台精确"
    elif dynamic_buckets >= max(1, total_buckets // 2):
        coverage = "公共广泛"
    elif selected:
        coverage = "最低可行"
    else:
        coverage = "阻断"
    metadata = {
        "dynamic_bucket_count": dynamic_buckets,
        "total_bucket_count": total_buckets,
        "dynamic_hits": dict(dynamic_hits),
        "fallback_hits": dict(fallback_hits),
        "selected_count": len(selected),
        "max_candidates_per_bucket": max_per_bucket,
    }
    return selected, coverage, metadata
