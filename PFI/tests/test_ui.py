from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

PFI_ROOT = Path(__file__).resolve().parents[1]
UI = PFI_ROOT / "src" / "pfi_os" / "ui.py"


def test_ui_renders_sample_data(monkeypatch) -> None:
    monkeypatch.setenv("PFI_DATA_DIR", str(PFI_ROOT / "examples" / "data"))
    app = AppTest.from_file(str(UI), default_timeout=30).run()
    assert not app.exception
    assert [h.value for h in app.header] == ["AUD", "CNY", "流水明细"]
    assert "入账 22 条" in app.caption[0].value


def test_ui_without_data_dir_asks_for_it(monkeypatch) -> None:
    monkeypatch.delenv("PFI_DATA_DIR", raising=False)
    app = AppTest.from_file(str(UI), default_timeout=30).run()
    assert not app.exception
    assert "PFI_DATA_DIR" in app.info[0].value
