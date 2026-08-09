\
from __future__ import annotations

import argparse
import io
import json
import sys
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version


EXPECTED = {
    "fastapi": "0.141.1",
    "starlette": "1.3.1",
    "uvicorn": "0.51.0",
    "SQLAlchemy": "2.0.51",
    "Jinja2": "3.1.6",
    "python-multipart": "0.0.32",
    "httpx": "0.28.1",
    "beautifulsoup4": "4.15.0",
    "pypdf": "6.14.2",
    "python-docx": "1.2.0",
    "argon2-cffi": "25.1.0",
    "cryptography": "50.0.0",
    "itsdangerous": "2.2.0",
}

IMPORTS = {
    "fastapi": "fastapi",
    "starlette": "starlette",
    "uvicorn": "uvicorn",
    "SQLAlchemy": "sqlalchemy",
    "Jinja2": "jinja2",
    "python-multipart": "multipart",
    "httpx": "httpx",
    "beautifulsoup4": "bs4",
    "pypdf": "pypdf",
    "python-docx": "docx",
    "argon2-cffi": "argon2",
    "cryptography": "cryptography",
    "itsdangerous": "itsdangerous",
}


def package_versions() -> tuple[dict[str, str], list[str]]:
    observed: dict[str, str] = {}
    errors: list[str] = []
    for package, expected in EXPECTED.items():
        try:
            actual = version(package)
        except PackageNotFoundError:
            actual = "MISSING"
        observed[package] = actual
        if actual != expected:
            errors.append(f"{package}: expected {expected}, observed {actual}")
        try:
            import_module(IMPORTS[package])
        except Exception as exc:  # pragma: no cover - target environment diagnostic
            errors.append(f"{package}: import failed: {type(exc).__name__}: {exc}")
    return observed, errors


def functional_checks() -> tuple[dict[str, str], list[str]]:
    checks: dict[str, str] = {}
    errors: list[str] = []

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/runtime-check")
        def runtime_check() -> dict[str, bool]:
            return {"ok": True}

        response = TestClient(app).get("/runtime-check")
        if response.status_code != 200 or response.json() != {"ok": True}:
            raise RuntimeError("FastAPI/Starlette request result mismatch")
        checks["fastapi_starlette_httpx"] = "PASS"
    except Exception as exc:
        checks["fastapi_starlette_httpx"] = "FAIL"
        errors.append(f"FastAPI/Starlette functional check failed: {type(exc).__name__}: {exc}")

    try:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        cipher = Fernet(key)
        payload = b"jobhuntos-runtime-check"
        if cipher.decrypt(cipher.encrypt(payload)) != payload:
            raise RuntimeError("Fernet round-trip mismatch")
        checks["fernet"] = "PASS"
    except Exception as exc:
        checks["fernet"] = "FAIL"
        errors.append(f"Fernet functional check failed: {type(exc).__name__}: {exc}")

    try:
        from pypdf import PdfReader, PdfWriter

        stream = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(stream)
        stream.seek(0)
        if len(PdfReader(stream).pages) != 1:
            raise RuntimeError("pypdf round-trip mismatch")
        checks["pypdf"] = "PASS"
    except Exception as exc:
        checks["pypdf"] = "FAIL"
        errors.append(f"pypdf functional check failed: {type(exc).__name__}: {exc}")

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.connect() as connection:
            value = connection.execute(text("select 1")).scalar_one()
        if value != 1:
            raise RuntimeError("SQLAlchemy result mismatch")
        checks["sqlalchemy_sqlite"] = "PASS"
    except Exception as exc:
        checks["sqlalchemy_sqlite"] = "FAIL"
        errors.append(f"SQLAlchemy functional check failed: {type(exc).__name__}: {exc}")

    try:
        from argon2 import PasswordHasher

        hasher = PasswordHasher()
        password = "Runtime-Only-Password-2026"
        if not hasher.verify(hasher.hash(password), password):
            raise RuntimeError("Argon2 verification mismatch")
        checks["argon2"] = "PASS"
    except Exception as exc:
        checks["argon2"] = "FAIL"
        errors.append(f"Argon2 functional check failed: {type(exc).__name__}: {exc}")

    try:
        from bs4 import BeautifulSoup
        from docx import Document
        from itsdangerous import URLSafeTimedSerializer

        if BeautifulSoup("<p>ok</p>", "html.parser").get_text(strip=True) != "ok":
            raise RuntimeError("BeautifulSoup parse mismatch")
        document = Document()
        document.add_paragraph("ok")
        buffer = io.BytesIO()
        document.save(buffer)
        if not buffer.getvalue():
            raise RuntimeError("python-docx output is empty")
        serializer = URLSafeTimedSerializer("runtime-only-secret")
        token = serializer.dumps({"ok": True})
        if serializer.loads(token) != {"ok": True}:
            raise RuntimeError("ItsDangerous round-trip mismatch")
        checks["supporting_libraries"] = "PASS"
    except Exception as exc:
        checks["supporting_libraries"] = "FAIL"
        errors.append(f"Supporting-library check failed: {type(exc).__name__}: {exc}")

    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the exact production Python runtime.")
    parser.add_argument("--expected-python", default="")
    args = parser.parse_args()

    observed, version_errors = package_versions()
    if args.expected_python and sys.version.split()[0] != args.expected_python:
        version_errors.append(
            f"python: expected {args.expected_python}, observed {sys.version.split()[0]}"
        )
    checks, functional_errors = functional_checks()
    errors = version_errors + functional_errors
    result = {
        "result": "PASS" if not errors else "FAIL",
        "python": sys.version.split()[0],
        "expected_versions": EXPECTED,
        "observed_versions": observed,
        "functional_checks": checks,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
