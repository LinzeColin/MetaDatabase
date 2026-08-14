from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
import httpx
from social_archive.config import Settings
from social_archive.connectors.http_workers import OpenAPIURLWorkerConnector, XHSWorkerConnector
from social_archive.connectors.oauth import RedditConnector, XConnector
from social_archive.utils import read_secret, utcnow


def core_loopback_url() -> str:
    raw_port = os.getenv('SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT', '18765').strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError('SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT 必须是端口号') from exc
    if not 1 <= port <= 65535:
        raise ValueError('SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT 必须介于 1 和 65535')
    return f'http://127.0.0.1:{port}'

def result(platform:str,status:str,details:dict)->dict:
    return {'schema_version':'1.0','platform':platform,'status':status,'time':utcnow(),'details':details}

def save(doc:dict)->None:
    results_dir = Settings.from_env().data_root / 'evidence/platform-canaries'
    results_dir.mkdir(parents=True,exist_ok=True);path=results_dir/f"{doc['platform']}.json";path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(doc,ensure_ascii=False))

def read_only_result(platform: str) -> dict:
    return result(platform, 'BLOCKED_ENVIRONMENT', {
        'error_code': 'OWNER_CANARY_NOT_AUTHORIZED',
        'next_action': 'Owner 明确授权最小只读 Canary 后再运行；当前 --read-only 不读取凭证、不访问网络、不写入 runtime。',
        'read_only': True,
        'credential_read': False,
        'network_attempted': False,
        'runtime_write': False,
    })

def core_capture_headers(settings: Settings) -> tuple[dict[str, str], dict[str, str] | None]:
    token = read_secret(settings.api_token_file)
    if settings.pairing_required and not token:
        return {}, {
            'error_code': 'API_TOKEN_MISSING',
            'next_action': '配置受限 API Token 后再运行 generic-web canary。',
        }
    return ({'Authorization': f'Bearer {token}'} if token else {}), None


def run_one(platform:str,limit:int,*,read_only: bool = False)->dict:
    if read_only:
        return read_only_result(platform)
    settings=Settings.from_env()
    if platform=='generic-web':
        headers, blocked = core_capture_headers(settings)
        if blocked:
            return result(platform, 'BLOCKED_ENVIRONMENT', blocked)
        try:
            r=httpx.post(f'{core_loopback_url()}/v1/captures',headers=headers,json={'platform':'generic-web','url':'https://www.wikipedia.org/wiki/Archiving','relation_type':'manual_save','title':'Social Archive Canary','text':'deterministic canary','requested_levels':['L0','L1']},timeout=10);r.raise_for_status();return result(platform,'PASS',{'content_id':r.json()['content_id']})
        except Exception as exc:return result(platform,'BLOCKED_ENVIRONMENT',{'error_type':exc.__class__.__name__,'next_action':'启动 core-api 后重跑'})
    if platform=='x':
        token=lambda:read_secret(os.getenv('SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE'));conn=XConnector(os.getenv('SOCIAL_ARCHIVE_X_USER_ID'),token);a=conn.fetch('bookmark',limit);b=conn.fetch('like',limit);status='PASS' if a.status in {'success','partial'} and b.status in {'success','partial'} else 'BLOCKED_ENVIRONMENT';return result(platform,status,{'bookmarks':a.__dict__,'likes':b.__dict__})
    if platform=='reddit':
        token=lambda:read_secret(os.getenv('SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE'));conn=RedditConnector(os.getenv('SOCIAL_ARCHIVE_REDDIT_USERNAME'),os.getenv('SOCIAL_ARCHIVE_REDDIT_USER_AGENT','SocialArchive/0.0.0.6'),token);a=conn.fetch('saved',limit);b=conn.fetch('upvoted',limit);status='PASS' if a.status in {'success','partial'} and b.status in {'success','partial'} else 'BLOCKED_ENVIRONMENT';return result(platform,status,{'saved':a.__dict__,'upvoted':b.__dict__})
    if platform=='instagram':
        session=Path(os.getenv('SOCIAL_ARCHIVE_INSTAGRAM_SESSION_FILE',''))
        if not session.is_file() or not shutil.which('instaloader'):return result(platform,'BLOCKED_ENVIRONMENT',{'next_action':'配置 0600 Instagram session 并安装 Instaloader'})
        return result(platform,'READY_FOR_OWNER_CANARY',{'session_present':True,'binary':shutil.which('instaloader'),'command_contract':['instaloader','--sessionfile',str(session),':saved']})
    if platform=='xiaohongshu':
        health=XHSWorkerConnector(settings.xhs_worker_url).health();return result(platform,'READY_FOR_OWNER_CANARY' if health.get('state')=='healthy' else 'DEGRADED',health)
    if platform=='douyin':
        health=OpenAPIURLWorkerConnector('douyin','抖音',settings.douk_worker_url).health();return result(platform,'READY_FOR_OWNER_CANARY' if health.get('state')=='healthy' else 'DEGRADED',health)
    if platform=='kuaishou':
        health=OpenAPIURLWorkerConnector('kuaishou','快手',settings.ks_worker_url).health();return result(platform,'READY_FOR_OWNER_CANARY' if health.get('state')=='healthy' else 'DEGRADED',health)
    if platform=='bilibili':
        binary=shutil.which('bili');return result(platform,'READY_FOR_OWNER_CANARY' if binary else 'BLOCKED_ENVIRONMENT',{'binary':binary,'allowed_commands':['favorites','watch-later','history']})
    if platform=='tiktok':
        bins={b:shutil.which(b) for b in ('gallery-dl','yt-dlp')};return result(platform,'READY_FOR_OWNER_CANARY' if any(bins.values()) else 'BLOCKED_ENVIRONMENT',bins)
    return result(platform,'NOT_APPLICABLE',{})

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('platform');ap.add_argument('--read-only',action='store_true',help='只输出 Owner 授权阻断状态；不读取凭证、不访问网络、不写入 runtime');ap.add_argument('--limit',type=int,default=3);args=ap.parse_args()
    platforms=['generic-web','x','reddit','instagram','tiktok','xiaohongshu','douyin','kuaishou','bilibili','youtube'] if args.platform in {'all','all-cn'} else [args.platform]
    if args.platform=='all-cn':platforms=['xiaohongshu','douyin','kuaishou','bilibili']
    docs=[run_one(p,args.limit,read_only=args.read_only) for p in platforms]
    if args.read_only:
        for doc in docs:print(json.dumps(doc,ensure_ascii=False))
    else:
        for doc in docs:save(doc)
    return 0 if all(d['status'] in {'PASS','READY_FOR_OWNER_CANARY','DEGRADED','BLOCKED_ENVIRONMENT'} for d in docs) else 1
if __name__=='__main__':raise SystemExit(main())
