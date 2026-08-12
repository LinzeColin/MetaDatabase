from pathlib import Path

from social_archive.models import CaptureRequest
def test_beginner_can_capture_without_platform_credentials(service,store):
    response=service.capture(CaptureRequest(platform='generic-web',url='https://www.wikipedia.org/start',title='第一条',requested_levels=['L0','L1']))
    items=store.list_library();assert response.content_id==items[0]['id'] and items[0]['title']=='第一条'


def test_start_script_tells_the_beginner_what_to_do_without_asking_for_input():
    """v0.0.0.7 / T03：原名 `..._prints_beginner_pairing_code`。

    原先 start.sh 会打印一串十分钟过期的配对码，让新手手抄进插件——
    实际使用中连续失败三次，且"手抄字符"本身就是 INV-ZERO-BARRIER 禁止的门槛。
    现在它只需告诉用户去哪，凭据由已登录页面自动交给插件。
    """
    root = Path(__file__).parents[2]
    text = (root / "scripts/start.sh").read_text(encoding="utf-8")
    assert "ensure_api_token.py" in text, "长期 API 令牌没人创建了"
    assert "一次性配对码" not in text
    assert "无需输入任何内容" in text
