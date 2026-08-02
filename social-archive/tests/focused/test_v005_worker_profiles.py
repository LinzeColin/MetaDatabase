from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_domestic_worker_profiles_are_runnable_and_health_gated():
    compose = yaml.safe_load((ROOT / "compose.workers.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "domestic-stable" in services["xhs-worker"]["profiles"]
    assert "domestic-stable" in services["ks-worker"]["profiles"]
    for name in ("xhs-worker", "ks-worker", "douk-worker"):
        assert services[name].get("healthcheck")
        assert services[name].get("security_opt") == ["no-new-privileges:true"]
    script = (ROOT / "scripts/start_workers.sh").read_text(encoding="utf-8")
    assert "vendor_sync.py --source xhs_downloader --source ks_downloader" in script
    assert '--profile "$profile"' in script
    assert "domestic-stable" in script


def test_worker_profiles_do_not_break_core_fallback():
    source = (ROOT / "src/social_archive/registry.py").read_text(encoding="utf-8")
    assert 'for tool in ("gallery-dl", "yt-dlp")' in source
    assert "通用网页" in source or "generic-web" in source
