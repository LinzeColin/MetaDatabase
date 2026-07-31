#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, socket
from datetime import datetime, timezone
from pathlib import Path


def canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    p=argparse.ArgumentParser();p.add_argument('--universe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    host=os.environ.get('MOOMOO_OPEND_HOST','127.0.0.1');port=int(os.environ.get('MOOMOO_OPEND_PORT','11111'))
    checks={'loopback':host in {'127.0.0.1','localhost','::1'},'license_confirmed':os.environ.get('SIGNAL_LATTICE_MARKET_LICENSE_CONFIRMED')=='1'}
    diagnostics={}
    code=None
    try:
        data=json.loads(a.universe.read_text());row=next(x for x in data['universe'] if x.get('active',True));market=str(row['market']).upper();symbol=str(row['symbol']).upper();code=symbol if symbol.startswith(market+'.') else f'{market}.{symbol}'
        with socket.create_connection((host,port),timeout=3): checks['tcp']=True
        try:
            from moomoo import OpenQuoteContext,RET_OK
        except ImportError:
            from futu import OpenQuoteContext,RET_OK
        ctx=OpenQuoteContext(host=host,port=port)
        try:
            ret,df=ctx.get_market_snapshot([code]);checks['quote_snapshot']=ret==RET_OK and df is not None and len(df.index)==1
            diagnostics['ret']=str(ret);diagnostics['code']=code
        finally:ctx.close()
    except Exception as exc:
        diagnostics['error']=type(exc).__name__+':'+str(exc)[:500]
    payload={'schema_version':'1.0.0','state':'PASS' if checks and all(checks.values()) else 'BLOCKED','verified_at':datetime.now(timezone.utc).isoformat(),'host':host,'port':port,'code':code,'checks':checks,'diagnostics':diagnostics,'trade_context_opened':False,'automatic_trading':False}
    payload['receipt_sha256']=hashlib.sha256(canonical(payload)).hexdigest();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n');os.chmod(a.output,0o600);print(json.dumps(payload,ensure_ascii=False,sort_keys=True));return 0 if payload['state']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
