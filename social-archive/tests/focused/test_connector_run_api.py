from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry

def test_generic_run_normalizes_to_capture(settings):
    result,captures=ConnectorRegistry(settings).run('generic-web',ConnectorRunRequest(url='https://www.wikipedia.org/x',requested_levels=['L0','L1']))
    assert result.status=='success' and len(captures)==1 and captures[0].platform=='generic-web'
