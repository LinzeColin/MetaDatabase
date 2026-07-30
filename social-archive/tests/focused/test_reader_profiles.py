from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from social_archive.models import CaptureRequest


ROOT = Path(__file__).resolve().parents[2]


def _script_env(settings, *, l2_enabled: bool) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{ROOT / 'src'}{os.pathsep}{existing}" if existing else str(ROOT / "src")
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOCIAL_ARCHIVE_ENV": "test",
            "SOCIAL_ARCHIVE_DATA_ROOT": str(settings.data_root),
            "SOCIAL_ARCHIVE_RUNTIME_DB": str(settings.runtime_db),
            "SOCIAL_ARCHIVE_STAGING_ROOT": str(settings.staging_root),
            "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": str(settings.private_database_root),
            "SOCIAL_ARCHIVE_WATCH_ROOT": str(settings.watch_root),
            "SOCIAL_ARCHIVE_EXPORT_ROOT": str(settings.export_root),
            "SOCIAL_ARCHIVE_PWA_ROOT": str(settings.pwa_root),
            "SOCIAL_ARCHIVE_L2_ENABLED": "true" if l2_enabled else "false",
        }
    )
    return env


def _run_wacz(settings, content_id: str, source: Path, *, l2_enabled: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "import_wacz.py"), content_id, str(source)],
        cwd=ROOT,
        env=_script_env(settings, l2_enabled=l2_enabled),
        capture_output=True,
        text=True,
        check=False,
    )

def test_reader_profiles_are_isolated_and_secret_backed():
    root=Path(__file__).resolve().parents[2]
    doc=yaml.safe_load((root/'compose.readers.yaml').read_text(encoding='utf-8'))
    services=doc['services']
    assert {'karakeep','karakeep-meilisearch','karakeep-chrome','linkwarden','linkwarden-postgres','archivebox'} <= set(services)
    assert services['karakeep']['env_file']==['./runtime/secrets/karakeep.env']
    assert services['linkwarden']['env_file']==['./runtime/secrets/linkwarden.env']
    assert 'social-archive' not in str(services['karakeep'].get('volumes',[]))


@pytest.mark.parametrize(
    ("profile", "required_secrets"),
    [
        ("archivebox", ()),
        ("karakeep", ("karakeep.env",)),
        ("linkwarden", ("linkwarden.env",)),
        ("readers", ("karakeep.env", "linkwarden.env")),
    ],
)
def test_reader_start_profiles_require_only_their_own_secrets(tmp_path: Path, profile: str, required_secrets: tuple[str, ...]):
    sandbox = tmp_path / "readers"
    scripts = sandbox / "scripts"
    scripts.mkdir(parents=True)
    start = scripts / "start_readers.sh"
    start.write_bytes((ROOT / "scripts" / "start_readers.sh").read_bytes())
    start.chmod(0o755)
    docker_bin = sandbox / "bin" / "docker"
    docker_bin.parent.mkdir()
    log = sandbox / "docker.log"
    docker_bin.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >> \"${FAKE_DOCKER_LOG:?}\"\n",
        encoding="utf-8",
    )
    docker_bin.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{docker_bin.parent}{os.pathsep}{env['PATH']}"
    env["FAKE_DOCKER_LOG"] = str(log)

    missing = subprocess.run(["/bin/bash", str(start), profile], cwd=sandbox, env=env, capture_output=True, text=True, check=False)
    if required_secrets:
        assert missing.returncode == 2
        assert not log.exists()
    else:
        assert missing.returncode == 0
        assert "--profile archivebox up -d" in log.read_text(encoding="utf-8")
        return

    secret_root = sandbox / "runtime" / "secrets"
    secret_root.mkdir(parents=True)
    for name in required_secrets:
        (secret_root / name).write_text("fixture\n", encoding="utf-8")
    started = subprocess.run(["/bin/bash", str(start), profile], cwd=sandbox, env=env, capture_output=True, text=True, check=False)
    assert started.returncode == 0
    assert f"--profile {profile} up -d" in log.read_text(encoding="utf-8")


def test_archivebox_sync_requires_explicit_l2_opt_in(tmp_path: Path):
    sandbox = tmp_path / "archivebox"
    scripts = sandbox / "scripts"
    scripts.mkdir(parents=True)
    sync = scripts / "archivebox_sync.sh"
    sync.write_bytes((ROOT / "scripts" / "archivebox_sync.sh").read_bytes())
    sync.chmod(0o755)
    queue = sandbox / "runtime" / "exports" / "readers" / "archivebox-urls.txt"
    queue.parent.mkdir(parents=True)
    queue.write_text("https://example.test/archivebox\n", encoding="utf-8")
    docker_bin = sandbox / "bin" / "docker"
    docker_bin.parent.mkdir()
    log = sandbox / "docker.log"
    docker_bin.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >> \"${FAKE_DOCKER_LOG:?}\"\n",
        encoding="utf-8",
    )
    docker_bin.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{docker_bin.parent}{os.pathsep}{env['PATH']}"
    env["FAKE_DOCKER_LOG"] = str(log)
    env.pop("SOCIAL_ARCHIVE_L2_ENABLED", None)

    blocked = subprocess.run(["/bin/bash", str(sync), str(queue)], cwd=sandbox, env=env, capture_output=True, text=True, check=False)
    assert blocked.returncode == 3
    assert "L2 默认关闭" in blocked.stderr
    assert not log.exists()

    env["SOCIAL_ARCHIVE_L2_ENABLED"] = "true"
    submitted = subprocess.run(["/bin/bash", str(sync), str(queue)], cwd=sandbox, env=env, capture_output=True, text=True, check=False)
    assert submitted.returncode == 0
    calls = log.read_text(encoding="utf-8")
    assert "compose -f compose.readers.yaml --profile archivebox up -d archivebox" in calls
    assert "archivebox add --parser=urls --depth=0" in calls


def test_archiveweb_wacz_is_blocked_before_reading_input_when_l2_is_off(settings, tmp_path: Path):
    missing = tmp_path / "missing.wacz"
    result = _run_wacz(settings, "cnt_missing", missing, l2_enabled=False)
    assert result.returncode == 3
    assert json.loads(result.stdout)["status"] == "BLOCKED_BY_DEFAULT"
    assert not settings.runtime_db.exists()
    assert not (settings.staging_root / "objects").exists()


def test_archiveweb_wacz_rejects_unknown_content_before_copying_file(settings, store, tmp_path: Path):
    source = tmp_path / "unknown.wacz"
    source.write_bytes(b"fixture WACZ")
    result = _run_wacz(settings, "cnt_missing", source, l2_enabled=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "CONTENT_NOT_FOUND"
    assert not (settings.staging_root / "objects").exists()
    with store.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM artifact").fetchone()[0] == 0


def test_archiveweb_wacz_import_is_an_explicit_l2_file_projection(settings, store, service, tmp_path: Path):
    content_id = service.capture(
        CaptureRequest(
            platform="generic_web",
            url="https://example.test/archiveweb",
            title="ArchiveWeb 文件投影",
            text="正文",
            requested_levels=["L0", "L1"],
            destination_ids=["social_archive"],
        )
    ).content_id
    before = store.get_content(content_id)
    assert before is not None
    canonical_before = {key: before[key] for key in ("id", "canonical_url", "title", "metadata_json")}
    source = tmp_path / "archiveweb.wacz"
    source.write_bytes(b"fixture WACZ payload")

    result = _run_wacz(settings, content_id, source, l2_enabled=True)
    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body["status"] == "PASS"
    assert body["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    after = store.get_content(content_id)
    assert after is not None
    assert {key: after[key] for key in canonical_before} == canonical_before
    artifacts = [item for item in after["artifacts"] if item["artifact_type"] == "wacz"]
    assert len(artifacts) == 1
    assert artifacts[0]["archive_level"] == "L2"
    assert Path(artifacts[0]["local_path"]).is_file()
