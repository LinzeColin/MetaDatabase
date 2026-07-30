import subprocess
from social_archive.connectors.command import CommandArtifactConnector

def test_bilibili_read_only_list(settings,monkeypatch):
    monkeypatch.setattr('subprocess.run',lambda argv,**kwargs: subprocess.CompletedProcess(argv,0,'[{"bvid":"BV1"}]',''))
    result=CommandArtifactConnector('bilibili',settings.staging_root).bilibili_list('favorites')
    assert result.status=='success' and result.observations[0]['bvid']=='BV1'
