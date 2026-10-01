from app.headless.mail import mail_config, maybe_send

CONFIG = {"host": "relay", "port": "2525", "from": "a@example.com", "to": "b@example.com"}
RESULT = {"run_id": "r1", "top5": ["270042"], "recommendations": [{"rank": 2, "asset_name": "乙", "asset_code": "2"}, {"rank": 1, "asset_name": "甲", "asset_code": "270042"}]}


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port):
        self.addr = (host, port)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, msg):
        FakeSMTP.sent.append((self.addr, msg))


def test_not_configured_without_host_or_recipient():
    assert mail_config({}) is None
    assert mail_config({"SERENITY_SMTP_HOST": "relay"}) is None
    assert mail_config({"SERENITY_SMTP_HOST": "relay", "SERENITY_MAIL_TO": "b@example.com"})["port"] == "25"


def test_sends_once_per_nav_date_and_skips_bad_data(tmp_path):
    FakeSMTP.sent = []
    ok = {"status": "ok", "latest_nav_date": "2026-09-30"}
    r = maybe_send(tmp_path, RESULT, ok, "<p>x</p>", "x", config=CONFIG, smtp_factory=FakeSMTP)
    assert r == {"mail": "sent", "nav_date": "2026-09-30"}
    (addr, msg), = FakeSMTP.sent
    assert addr == ("relay", 2525) and msg["To"] == "b@example.com"
    assert "第一名 甲（270042）" in msg["Subject"] and "2026-09-30" in msg["Subject"]
    assert maybe_send(tmp_path, RESULT, ok, "<p>x</p>", "x", config=CONFIG, smtp_factory=FakeSMTP)["mail"] == "skipped_same_nav_date"
    bad = {"status": "degraded", "latest_nav_date": "2026-10-01"}
    assert maybe_send(tmp_path, RESULT, bad, "", "", config=CONFIG, smtp_factory=FakeSMTP)["mail"] == "skipped_data_not_ok"
    newer = {"status": "ok", "latest_nav_date": "2026-10-01"}
    assert maybe_send(tmp_path, RESULT, newer, "", "", config=CONFIG, smtp_factory=FakeSMTP)["mail"] == "sent"
    assert len(FakeSMTP.sent) == 2
