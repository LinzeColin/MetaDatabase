from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from signal_lattice_v19.config import Settings


@contextmanager
def fixture_settings(project_root: Path):
    with TemporaryDirectory() as tmp:
        keys = {
            "SL19_STATE_DIR": tmp,
            "SL19_CONFIG_DIR": str(project_root / "config"),
            "SL19_WEB_DIR": str(project_root / "web"),
            "SL19_FIXTURE_DIR": str(project_root / "fixtures"),
            "SL19_MARKET_PROVIDER": "fixture",
            "SL19_HOST": "127.0.0.1",
            "SL19_PORT": "18787",
        }
        old = {key: os.environ.get(key) for key in keys}
        os.environ.update(keys)
        try:
            yield Settings.from_env(project_root), Path(tmp)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
