from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _dockerignore_patterns() -> set[str]:
    return {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_docker_build_context_excludes_credentials_runtime_and_caches():
    patterns = _dockerignore_patterns()
    required = {
        ".git/",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*credentials*.json",
        "*cookies*.json",
        "runtime/",
        "*.sqlite3",
        ".venv/",
        "node_modules/",
        "__pycache__/",
        ".pytest_cache/",
        "evidence/",
    }
    assert required <= patterns


def test_dockerfile_uses_explicit_first_party_copy_paths():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . " not in dockerfile
    for expected in (
        "COPY pyproject.toml README.md VERSION ./",
        "COPY src ./src",
        "COPY apps ./apps",
        "COPY scripts ./scripts",
    ):
        assert expected in dockerfile
