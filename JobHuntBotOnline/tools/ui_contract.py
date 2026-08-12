#!/usr/bin/env python3
"""Static UI contract audit over every shipped Jinja template and FastAPI route."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import with a deterministic test configuration so route discovery never needs
# production Secret or SMTP values.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("SESSION_SECRET", "ui-contract-session")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("EMAIL_LOOKUP_SECRET", "ui-contract-email")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass!2026")
os.environ.setdefault("DISCOVERY_REFRESH_HOURS", "6")
os.environ.setdefault("ENABLE_REMOTIVE", "false")
os.environ.setdefault("ENABLE_ARBEITNOW", "false")
os.environ.setdefault("ENABLE_JOBICY", "false")

from app.main import create_app


def normalize_route(path: str) -> str:
    return re.sub(r"\{[^/]+\}", "{param}", path.rstrip("/") or "/")


def action_matches(action: str, routes: set[str]) -> bool:
    if not action or "{{" in action or "{%" in action:
        return True
    if not action.startswith("/"):
        return False
    candidate = re.sub(r"/\d+(?=/|$)", "/{param}", action.rstrip("/") or "/")
    return candidate in routes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/local/ui_contract.json")
    args = parser.parse_args()

    app = create_app()
    post_routes = {normalize_route(route.path) for route in app.routes if "POST" in getattr(route, "methods", set())}
    get_routes = {normalize_route(route.path) for route in app.routes if "GET" in getattr(route, "methods", set())}
    errors: list[str] = []
    warnings: list[str] = []
    totals = {"templates": 0, "forms": 0, "buttons": 0, "inputs": 0, "links": 0, "testids": 0}
    testids: set[str] = set()

    for template in sorted((ROOT / "app/templates").glob("*.html")):
        totals["templates"] += 1
        soup = BeautifulSoup(template.read_text(encoding="utf-8"), "html.parser")
        for form in soup.find_all("form"):
            totals["forms"] += 1
            method = (form.get("method") or "get").casefold()
            action = form.get("action") or ""
            if method not in {"get", "post"}:
                errors.append(f"{template.name}: unsupported form method {method}")
            routes = post_routes if method == "post" else get_routes
            if not action_matches(action, routes):
                errors.append(f"{template.name}: form action has no matching route: {method.upper()} {action}")
            if method == "post" and not form.find("input", attrs={"name": "csrf_token"}):
                errors.append(f"{template.name}: POST form is missing csrf_token")
            submit = form.find(["button", "input"], attrs={"type": "submit"})
            if submit is None:
                errors.append(f"{template.name}: form has no submit control")

        for node in soup.find_all(["input", "select", "textarea"]):
            totals["inputs"] += 1
            input_type = (node.get("type") or "").casefold()
            if input_type not in {"button", "submit", "reset"} and not node.get("name"):
                errors.append(f"{template.name}: input/select/textarea without name")
            if node.has_attr("required") and input_type == "hidden":
                warnings.append(f"{template.name}: required hidden input")

        for button in soup.find_all("button"):
            totals["buttons"] += 1
            if not button.get_text(" ", strip=True) and not button.get("aria-label"):
                errors.append(f"{template.name}: unlabeled button")
            if button.get("type", "submit") == "button" and not (
                button.get("data-copy") or button.get("data-action") or button.get("aria-controls")
            ):
                errors.append(f"{template.name}: type=button has no declared behavior")

        for link in soup.find_all("a"):
            totals["links"] += 1
            href = link.get("href")
            if href in {None, "", "#"}:
                errors.append(f"{template.name}: empty/dead link")
            if not link.get_text(" ", strip=True) and not link.get("aria-label"):
                errors.append(f"{template.name}: unlabeled link")

        for node in soup.select("[data-testid]"):
            totals["testids"] += 1
            value = str(node.get("data-testid"))
            if value in testids and "{{" not in value:
                warnings.append(f"duplicate testid across templates: {value}")
            testids.add(value)

    required_testids = {
        "register-submit", "login-submit", "forgot-submit", "reset-submit",
        "resume-upload-submit", "confirm-submit", "refresh-recommendations",
        "filter-q", "filter-city", "filter-role", "filter-skill", "filter-source",
        "filter-freshness", "filter-qualification", "filter-relevance",
        "filter-opportunity", "filter-status", "filter-submit", "job-card",
        "job-detail-link", "save-job", "ignore-job", "create-pack",
        "manual-submit", "application-submit", "data-export", "delete-account-submit",
        "admin-users-table", "admin-platform-link",
    }
    missing_testids = sorted(required_testids - testids)
    if missing_testids:
        errors.append("missing required testids: " + ", ".join(missing_testids))

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "scope": "all shipped Jinja forms, controls, links, data-testid hooks and FastAPI route bindings",
        "totals": totals,
        "errors": errors,
        "warnings": sorted(set(warnings)),
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
