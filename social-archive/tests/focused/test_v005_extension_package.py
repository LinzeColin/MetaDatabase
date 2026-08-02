from pathlib import Path
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def test_extension_package_builds_and_contains_installable_root():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/build_extension_package.py")], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    archive = Path(payload["output"])
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "popup.html", "background.js", "bridge.js", "content/extract-core.js"} <= names
        assert not any(name.startswith("browser-extension/") for name in names)
