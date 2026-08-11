from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import validate_settings
from app.security import hash_password, validate_password, verify_password


def test_refresh_contract_is_exactly_six_hours(settings):
    validate_settings(settings)
    with pytest.raises(RuntimeError):
        validate_settings(replace(settings, discovery_refresh_hours=5))
    with pytest.raises(RuntimeError):
        validate_settings(replace(settings, discovery_refresh_hours=12))


def test_password_contract():
    assert validate_password("short") is not None
    assert validate_password("alllowercase123") is not None
    assert validate_password("NoNumberPassword") is not None
    assert validate_password("ValidPass123") is None
    hashed = hash_password("ValidPass123")
    assert verify_password(hashed, "ValidPass123")
    assert not verify_password(hashed, "WrongPass123")
