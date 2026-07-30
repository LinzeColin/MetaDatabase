import json
from pathlib import Path

from social_archive.exports import StandardExporter
from social_archive.models import CaptureRequest


def test_standard_exports_include_portable_jsonl_markdown_and_stable_noop(service, store, tmp_path):
    captured = service.capture(
        CaptureRequest(
            platform="x",
            url="https://x.com/a/status/1",
            relation_type="bookmark",
            title="标题",
            text="可恢复的正文",
            requested_levels=["L0", "L1"],
        )
    )
    output = tmp_path / "out"
    exporter = StandardExporter(store, output)

    first = exporter.export_all()
    assert first["status"] == "done"
    assert first["item_count"] == 1
    for name in (
        "library.jsonl",
        "notion-import.csv",
        "bookmarks.html",
        "archivebox-urls.txt",
        "feed.json",
        "EXPORT_MANIFEST.json",
    ):
        assert (output / name).is_file()
    markdown = next((output / "obsidian-vault").glob("*.md"))
    assert "可恢复的正文" in markdown.read_text(encoding="utf-8")
    records = [json.loads(line) for line in (output / "library.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["content_id"] == captured.content_id
    assert records[0]["canonical_url"] == "https://x.com/a/status/1"
    assert records[0]["platform"] == "x"
    assert records[0]["relation_type"] == "bookmark"
    assert records[0]["collection_key"] is None
    assert records[0]["text"] == "可恢复的正文"
    assert records[0]["metadata"] == {}
    assert records[0]["first_observed_at"] and records[0]["last_observed_at"]
    manifest_before = json.loads((output / "EXPORT_MANIFEST.json").read_text(encoding="utf-8"))
    assert "library.jsonl" in manifest_before["outputs"]
    assert len(manifest_before["snapshot_sha256"]) == 64

    second = exporter.export_all()
    manifest_after = json.loads((output / "EXPORT_MANIFEST.json").read_text(encoding="utf-8"))
    assert second["status"] == "noop"
    assert second["changed_files"] == 0
    assert manifest_after == manifest_before


def test_export_script_uses_configured_export_root():
    root = Path(__file__).parents[2]
    source = (root / "scripts/export_all.py").read_text(encoding="utf-8")
    assert "StandardExporter(store, settings.export_root)" in source
