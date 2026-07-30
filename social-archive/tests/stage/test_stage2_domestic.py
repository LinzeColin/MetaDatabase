from pathlib import Path
import yaml
from social_archive.registry import ConnectorRegistry


def test_domestic_workers_are_independently_registered_and_orchestrated(settings):
    registry = ConnectorRegistry(settings)
    assert set(registry._connectors) == {"xiaohongshu","kuaishou","douyin"}
    assert registry._connectors["xiaohongshu"] is not registry._connectors["douyin"]
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "compose.workers.yaml").read_text(encoding="utf-8"))
    assert {"xhs-worker","ks-worker","douk-worker"} <= set(compose["services"])
