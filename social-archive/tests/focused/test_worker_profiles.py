from pathlib import Path
import yaml


def test_domestic_workers_are_source_built_and_disabled_by_profile():
    root = Path(__file__).resolve().parents[2]
    doc = yaml.safe_load((root / "compose.workers.yaml").read_text(encoding="utf-8"))
    services = doc["services"]
    assert services["xhs-worker"]["build"]["context"].endswith("runtime/vendors/XHS-Downloader")
    assert services["ks-worker"]["build"]["context"].endswith("runtime/vendors/KS-Downloader")
    assert services["douk-worker"]["profiles"] == ["douk-experimental"]
    assert all(item["image"].startswith("social-archive/") for item in services.values())


def test_cli_downloaders_are_isolated_from_core_image():
    root = Path(__file__).resolve().parents[2]
    core = (root / "Dockerfile").read_text(encoding="utf-8")
    sidecar = (root / "sidecars/cli-tools/Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    assert all(tool not in core for tool in ("gallery-dl==", "yt-dlp==", "instaloader=="))
    assert all(tool in sidecar for tool in ("gallery-dl==", "yt-dlp==", "instaloader=="))
    assert "cli-tools" in compose["services"]
    assert "ports" not in compose["services"]["cli-tools"]
