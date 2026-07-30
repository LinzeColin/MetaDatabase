from social_archive.models import CaptureRequest

def test_capture_creates_relation_l1_and_l3_job(service,store):
    response=service.capture(CaptureRequest(platform='generic-web',url='https://www.wikipedia.org/a?utm_source=x',relation_type='manual_save',title='示例',text='正文',requested_levels=['L0','L1','L3']))
    assert response.content_id.startswith('cnt_');assert response.relation_id.startswith('rel_');assert response.job_ids
    item=store.get_content(response.content_id);assert item and len(item['relations'])==1;assert any(a['archive_level']=='L1' for a in item['artifacts'])
    assert item['canonical_url']=='https://www.wikipedia.org/a'

def test_idempotent_capture_does_not_duplicate_relation(service,store):
    req=CaptureRequest(platform='x',url='https://x.com/u/status/1',relation_type='bookmark',title='x')
    a=service.capture(req);b=service.capture(req);assert a.content_id==b.content_id and a.relation_id==b.relation_id
    assert len(store.get_content(a.content_id)['relations'])==1
