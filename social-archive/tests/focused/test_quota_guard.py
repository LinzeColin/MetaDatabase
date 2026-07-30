from dataclasses import replace
from social_archive.quota import QuotaGuard

def test_hard_quota_pauses_l3_only(settings,store):
    settings=replace(settings,r2_soft_bytes=1,r2_hard_bytes=2);settings.staging_root.mkdir(parents=True,exist_ok=True);(settings.staging_root/'x').write_bytes(b'123')
    d=QuotaGuard(settings,store).evaluate_local_staging();assert not d.allow_l3 and d.action=='pause_l3'
