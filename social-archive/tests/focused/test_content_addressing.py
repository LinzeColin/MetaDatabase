from social_archive.storage import ContentAddressedStore

def test_same_bytes_deduplicate(tmp_path):
    store=ContentAddressedStore(tmp_path);a=store.put_bytes(b'abc',suffix='.txt');b=store.put_bytes(b'abc',suffix='.txt')
    assert a.sha256==b.sha256 and a.path==b.path and a.path.read_bytes()==b'abc'
