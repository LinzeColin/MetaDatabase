from __future__ import annotations
import os
from dataclasses import replace
from pathlib import Path
import pytest
from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.service import ArchiveService

@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    root=tmp_path/'data'; pwa=tmp_path/'pwa';pwa.mkdir()
    s=Settings(env='test',host='127.0.0.1',port=8765,data_root=root,runtime_db=root/'runtime/db.sqlite3',staging_root=root/'staging',private_database_root=root/'private-database',pwa_root=pwa,watch_root=root/'import',export_root=root/'exports',log_level='INFO',paid_api_allowed=False,l2_enabled=False,l3_enabled=True,r2_soft_bytes=100_000_000,r2_hard_bytes=200_000_000,oci_soft_bytes=300_000_000,oci_hard_bytes=400_000_000,github_release_soft_bytes=100_000_000,github_release_hard_bytes=200_000_000,max_download_bytes=10_000_000,worker_poll_seconds=.01,xhs_worker_url='http://127.0.0.1:5556',douk_worker_url='http://127.0.0.1:5555',ks_worker_url='http://127.0.0.1:5557',cli_worker_url='',cli_worker_token_file=None,cli_output_root=root/'vendor-output/cli')
    s.ensure_directories();return s

@pytest.fixture
def store(settings: Settings) -> RuntimeStore:
    db=RuntimeStore(settings.runtime_db);db.initialize();return db

@pytest.fixture
def service(settings: Settings, store: RuntimeStore) -> ArchiveService:
    return ArchiveService(settings,store)
