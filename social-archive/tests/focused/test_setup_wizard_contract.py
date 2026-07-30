from pathlib import Path


def test_setup_wizard_is_secret_safe_and_install_entry_is_non_blocking():
    root = Path(__file__).parents[2]
    wizard = (root / "scripts/setup_wizard.py").read_text(encoding="utf-8")
    install = (root / "scripts/install.sh").read_text(encoding="utf-8")
    assert "getpass.getpass" in wizard
    assert "chmod(0o600)" in wizard
    assert "配置存在不等于已连接" in wizard
    assert "--non-interactive" in install
    assert "-t 0" in install
    assert "SOCIAL_ARCHIVE_SKIP_WIZARD" in install
