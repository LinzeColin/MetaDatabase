from pathlib import Path

from social_archive.models import CaptureRequest
def test_beginner_can_capture_without_platform_credentials(service,store):
    response=service.capture(CaptureRequest(platform='generic-web',url='https://www.wikipedia.org/start',title='第一条',requested_levels=['L0','L1']))
    items=store.list_library();assert response.content_id==items[0]['id'] and items[0]['title']=='第一条'


def test_start_script_prints_beginner_pairing_code():
    root = Path(__file__).parents[2]
    text = (root / "scripts/start.sh").read_text(encoding="utf-8")
    assert "generate_pairing_code.py" in text
    assert "一次性配对码" in text
