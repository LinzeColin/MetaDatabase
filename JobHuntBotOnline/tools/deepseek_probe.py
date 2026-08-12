#!/usr/bin/env python3
"""Run one synthetic DeepSeek request without exposing the platform key."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-unconfigured", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.deepseek_api_key:
        result = {"verdict": "BLOCKED", "configured": False, "model": settings.deepseek_model, "key_exposed": False}
        code = 0 if args.allow_unconfigured else 2
    else:
        try:
            response = httpx.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": "Return only JOBHUNT_OK."},
                        {"role": "user", "content": "Synthetic provider connectivity test."},
                    ],
                    "temperature": 0, "max_tokens": 20,
                },
                timeout=settings.deepseek_request_timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            ok = "JOBHUNT_OK" in content
            result = {
                "verdict": "PASS" if ok else "FAIL", "configured": True,
                "model": settings.deepseek_model, "provider_status": response.status_code,
                "response_contract": "PASS" if ok else "FAIL", "key_exposed": False,
            }
            code = 0 if ok else 1
        except Exception as exc:
            result = {
                "verdict": "FAIL", "configured": True, "model": settings.deepseek_model,
                "error_type": type(exc).__name__, "key_exposed": False,
            }
            code = 1
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = Path(args.output)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
