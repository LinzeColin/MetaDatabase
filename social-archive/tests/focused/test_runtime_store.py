from social_archive.models import CaptureRequest

def test_job_claim_and_finish(store):
    jid=store.enqueue_job('download_l3',{'content_id':'c','page_url':'https://www.wikipedia.org','media_urls':[]},'generic')
    row=store.claim_job('tester');assert row and row['id']==jid
    store.finish_job(jid,success=True);assert store.get_job(jid)['status']=='done'

def test_complete_scan_requires_two_absences(service,store):
    r=service.capture(CaptureRequest(platform='reddit',url='https://reddit.com/r/a/comments/1',relation_type='saved',requested_levels=['L0','L1']))
    store.apply_complete_scan('reddit',set(),relation_type='saved');assert store.get_content(r.content_id)['relations'][0]['status']=='active'
    store.apply_complete_scan('reddit',set(),relation_type='saved');assert store.get_content(r.content_id)['relations'][0]['status']=='closed'
