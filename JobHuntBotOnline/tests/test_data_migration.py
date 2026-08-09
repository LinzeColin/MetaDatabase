from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal
from app.models import AIApplicationEnhancement, AIProviderConfig, CandidateProfile, Resume
from app.services.data_migration import migrate_sensitive_storage, verify_sensitive_storage
from tests.test_routes import create_job


def test_legacy_plaintext_and_named_upload_are_migrated(ready_workspace):
    settings = get_settings()
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))

    with SessionLocal() as db:
        resume = db.scalar(select(Resume).limit(1))
        assert resume is not None
        opaque_path = Path(resume.encrypted_file_path)
        legacy_path = opaque_path.with_name("legacy-token_original-private-name.pdf.bin")
        opaque_path.rename(legacy_path)
        db.execute(
            text(
                "UPDATE candidate_profiles SET preferred_name = :name, sponsorship_now = :sponsor "
                "WHERE id = (SELECT id FROM candidate_profiles LIMIT 1)"
            ),
            {"name": "Legacy Private Name", "sponsor": 0},
        )
        db.execute(
            text("UPDATE resumes SET source_filename = :filename, encrypted_file_path = :path WHERE id = :id"),
            {"filename": "legacy-private-resume.pdf", "path": str(legacy_path), "id": resume.id},
        )
        db.commit()

    with SessionLocal() as db:
        result = migrate_sensitive_storage(db)
        profile = db.scalar(select(CandidateProfile).limit(1))
        migrated_resume = db.scalar(select(Resume).limit(1))
        assert profile is not None
        assert migrated_resume is not None
        assert profile.preferred_name == "Legacy Private Name"
        assert profile.sponsorship_now is False
        assert migrated_resume.source_filename == "legacy-private-resume.pdf"
        migrated_path = Path(migrated_resume.encrypted_file_path)
        verification = verify_sensitive_storage(db)

    assert verification["protected_fields"] >= 3
    assert verification["upload_objects"] == 1
    assert result["encrypted_fields"] >= 3
    assert result["renamed_uploads"] == 1
    assert not legacy_path.exists()
    assert migrated_path.is_file()
    assert re.fullmatch(r"[0-9a-f]{40}\.bin", migrated_path.name)

    connection = sqlite3.connect(database_path)
    try:
        raw_profile = connection.execute(
            "SELECT preferred_name, sponsorship_now FROM candidate_profiles LIMIT 1"
        ).fetchone()
        raw_resume = connection.execute(
            "SELECT source_filename, encrypted_file_path FROM resumes LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    assert raw_profile is not None and raw_resume is not None
    assert all(str(value).startswith("enc:v1:") for value in raw_profile)
    assert str(raw_resume[0]).startswith("enc:v1:")
    assert "legacy-private-resume.pdf" not in str(raw_resume[1])



def test_legacy_plaintext_deepseek_key_and_ai_content_are_migrated(ready_workspace):
    job_id = create_job(ready_workspace)
    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile).limit(1))
        assert profile is not None
        config = db.scalar(select(AIProviderConfig).where(AIProviderConfig.user_id == profile.user_id))
        assert config is not None
        config.api_key = "initial-test-secret-value"
        config.last_error = "initial error"
        enhancement = AIApplicationEnhancement(
            user_id=profile.user_id,
            job_id=job_id,
            model="deepseek-v4-flash",
            status="success",
            content_json='{"summary_zh":"private candidate result"}',
            usage_json='{"total_tokens":10}',
            error_message="",
        )
        db.add_all([config, enhancement])
        db.commit()
        db.execute(
            text("UPDATE ai_provider_configs SET api_key = :key, last_error = :error WHERE id = :id"),
            {"key": "legacy-plaintext-deepseek-key", "error": "legacy private provider error", "id": config.id},
        )
        db.execute(
            text(
                "UPDATE ai_application_enhancements SET content_json = :content, usage_json = :usage, "
                "error_message = :error WHERE id = :id"
            ),
            {
                "content": '{"summary_zh":"legacy private candidate result"}',
                "usage": '{"total_tokens":11}',
                "error": "legacy private AI error",
                "id": enhancement.id,
            },
        )
        db.commit()

    with SessionLocal() as db:
        result = migrate_sensitive_storage(db)
        verification = verify_sensitive_storage(db)
        config = db.scalar(select(AIProviderConfig))
        enhancement = db.scalar(select(AIApplicationEnhancement))
        assert config is not None and config.api_key == "legacy-plaintext-deepseek-key"
        assert enhancement is not None and "legacy private candidate result" in enhancement.content_json
        assert result["encrypted_fields"] >= 5
        assert verification["protected_fields"] >= 5
        raw_config = db.execute(text("SELECT api_key, last_error FROM ai_provider_configs LIMIT 1")).one()
        raw_ai = db.execute(
            text("SELECT content_json, usage_json, error_message FROM ai_application_enhancements LIMIT 1")
        ).one()
        assert all(str(value).startswith("enc:v1:") for value in raw_config)
        assert all(str(value).startswith("enc:v1:") for value in raw_ai)
