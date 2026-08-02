from __future__ import annotations

import uuid
from typing import Any, Callable

import httpx

from .base import ConnectorResult


def _retry_after_seconds(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        return None


class PaginatedOAuthConnector:
    def __init__(self, connector_id: str, display_name: str, token_provider: Callable[[], str | None]):
        self.connector_id = connector_id
        self.display_name = display_name
        self.token_provider = token_provider

    def _token(self) -> str | None:
        token = self.token_provider()
        return token.strip() if token else None

    def health(self) -> dict[str, Any]:
        return {"state":"healthy" if self._token() else "blocked_environment","auth_gate":"pass" if self._token() else "unknown"}


class XConnector(PaginatedOAuthConnector):
    def __init__(self, user_id: str | None, token_provider: Callable[[], str | None]):
        super().__init__("x", "X", token_provider)
        self.user_id = user_id

    def fetch(self, relation: str, limit: int = 100) -> ConnectorResult:
        run_id = str(uuid.uuid4())
        token = self._token()
        if not token or not self.user_id:
            return ConnectorResult(self.connector_id, run_id, "blocked_environment", scan_receipt={"completeness":"unknown","item_count":0}, errors=[{"code":"X_AUTH_MISSING","message":"缺少 X OAuth token 或 user id","retryable":False}])
        endpoint = "bookmarks" if relation == "bookmark" else "liked_tweets"
        url = f"https://api.x.com/2/users/{self.user_id}/{endpoint}"
        params = {"max_results":min(max(limit,5),100),"tweet.fields":"created_at,author_id,attachments,entities,note_tweet","expansions":"author_id,attachments.media_keys","media.fields":"url,preview_image_url,type"}
        try:
            with httpx.Client(timeout=30.0, headers={"Authorization":f"Bearer {token}"}) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            return ConnectorResult(self.connector_id, run_id, "partial", scan_receipt={"completeness":"partial","item_count":0}, errors=[{"code":"X_API_FAILED","message":str(exc),"retryable":True}])
        observations = [{"relation_type":relation, **item} for item in data.get("data", [])]
        complete = not bool((data.get("meta") or {}).get("next_token"))
        return ConnectorResult(self.connector_id, run_id, "success" if complete else "partial", observations=observations, scan_receipt={"completeness":"complete" if complete else "partial","item_count":len(observations),"next_token":(data.get("meta") or {}).get("next_token"),"scope":"account_relation","relation_type":relation})


class RedditConnector(PaginatedOAuthConnector):
    def __init__(self, username: str | None, user_agent: str, token_provider: Callable[[], str | None]):
        super().__init__("reddit", "Reddit", token_provider)
        self.username = username
        self.user_agent = user_agent

    def fetch(self, relation: str, limit: int = 100, cursor: str | None = None) -> ConnectorResult:
        run_id = str(uuid.uuid4())
        token = self._token()
        if not token or not self.username:
            return ConnectorResult(self.connector_id, run_id, "blocked_environment", scan_receipt={"completeness":"unknown","item_count":0}, errors=[{"code":"REDDIT_AUTH_MISSING","message":"缺少 Reddit OAuth token 或 username","retryable":False}])
        endpoint = "saved" if relation == "saved" else "upvoted"
        url = f"https://oauth.reddit.com/user/{self.username}/{endpoint}"
        headers = {"Authorization":f"Bearer {token}","User-Agent":self.user_agent}
        page_cursor = cursor.strip() if cursor else None
        params: dict[str, Any] = {"limit":min(max(limit,1),100),"raw_json":1}
        if page_cursor:
            params["after"] = page_cursor
        try:
            with httpx.Client(timeout=30.0, headers=headers) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                receipt: dict[str, Any] = {
                    "completeness":"unknown",
                    "item_count":0,
                    "scope":"account_relation",
                    "relation_type":relation,
                    "failure_code":"REDDIT_RATE_LIMITED",
                }
                if page_cursor:
                    receipt["cursor_start"] = page_cursor
                retry_after_seconds = _retry_after_seconds(exc.response)
                if retry_after_seconds is not None:
                    receipt["retry_after_seconds"] = retry_after_seconds
                return ConnectorResult(
                    self.connector_id,
                    run_id,
                    "partial",
                    scan_receipt=receipt,
                    errors=[{"code":"REDDIT_RATE_LIMITED","message":"Reddit 限流；保留检查点后稍后重试","retryable":True}],
                )
            receipt = {
                "completeness":"unknown",
                "item_count":0,
                "scope":"account_relation",
                "relation_type":relation,
                "failure_code":"REDDIT_API_FAILED",
            }
            if page_cursor:
                receipt["cursor_start"] = page_cursor
            return ConnectorResult(self.connector_id, run_id, "partial", scan_receipt=receipt, errors=[{"code":"REDDIT_API_FAILED","message":str(exc),"retryable":True}])
        except httpx.HTTPError as exc:
            receipt = {
                "completeness":"unknown",
                "item_count":0,
                "scope":"account_relation",
                "relation_type":relation,
                "failure_code":"REDDIT_API_FAILED",
            }
            if page_cursor:
                receipt["cursor_start"] = page_cursor
            return ConnectorResult(self.connector_id, run_id, "partial", scan_receipt=receipt, errors=[{"code":"REDDIT_API_FAILED","message":str(exc),"retryable":True}])
        children = ((data.get("data") or {}).get("children") or [])
        observations = [{"relation_type":relation,"kind":item.get("kind"),**(item.get("data") or {})} for item in children]
        after = (data.get("data") or {}).get("after")
        receipt = {
            "completeness":"complete" if not after else "partial",
            "item_count":len(observations),
            "next_cursor":after,
            "scope":"account_relation",
            "relation_type":relation,
        }
        if page_cursor:
            receipt["cursor_start"] = page_cursor
        return ConnectorResult(self.connector_id, run_id, "success" if not after else "partial", observations=observations, scan_receipt=receipt)
