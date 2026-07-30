#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--code',required=True,help='Moomoo code such as US.NVDA')
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=11111)
    p.add_argument('--usd-fx-rate',type=float,default=1.0)
    p.add_argument('--capacity-ratio',type=float,default=0.01)
    p.add_argument('--upstream-seal-pass',action='store_true')
    p.add_argument('--license-ack',action='store_true',help='确认当前账户与市场数据许可允许本项目按本用途读取并使用该报价')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not (0 < a.usd_fx_rate <= 1000 and 0 < a.capacity_ratio <= 0.05):
        raise SystemExit('INVALID_CONVERSION_OR_CAPACITY')
    try:
        from moomoo import OpenQuoteContext, RET_OK, SubType
    except ImportError:
        print(json.dumps({'state':'BLOCKED','reason':'MOOMOO_API_NOT_INSTALLED','install':'pip install -r requirements/providers-moomoo.txt'}))
        return 2
    ctx=OpenQuoteContext(host=a.host,port=a.port)
    try:
        ret,msg=ctx.subscribe([a.code],[SubType.QUOTE],subscribe_push=False)
        if ret!=RET_OK:
            raise RuntimeError('MOOMOO_SUBSCRIBE_FAILED:'+str(msg))
        ret,data=ctx.get_stock_quote([a.code])
        if ret!=RET_OK or data is None or len(data.index)!=1:
            raise RuntimeError('MOOMOO_QUOTE_FAILED:'+str(data))
        row=data.iloc[0].to_dict()
    finally:
        ctx.close()
    now=datetime.now(timezone.utc)
    price=float(row.get('last_price') or row.get('cur_price') or 0)
    turnover=float(row.get('turnover') or 0)
    if price<=0 or turnover<0:
        raise RuntimeError('MOOMOO_QUOTE_FIELDS_INVALID')
    source_payload={'code':a.code,'data_date':str(row.get('data_date','')),'data_time':str(row.get('data_time','')),'last_price':price,'turnover':turnover}
    digest=hashlib.sha256(json.dumps(source_payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    market=a.code.split('.',1)[0].upper()
    symbol=a.code.split('.',1)[1].upper() if '.' in a.code else a.code.upper()
    license_ack=bool(a.license_ack or os.environ.get('SIGNAL_LATTICE_MOOMOO_LICENSE_ACK')=='1')
    snapshot={
        'symbol':symbol,'market':market,'as_of':now.isoformat(),'available_at':now.isoformat(),'ingested_at':now.isoformat(),
        'price':price,'currency':'USD' if market=='US' else 'LOCAL','daily_value_traded_usd':turnover*a.usd_fx_rate,
        'capacity_usd':turnover*a.usd_fx_rate*a.capacity_ratio,'point_in_time_ok':True,'license_ok':license_ack,
        'freshness_seconds':0,'spread_bps':0,'slippage_bps':5,'source':'MOOMOO_OPEND','source_digest':digest,
        'upstream_seal_pass':bool(a.upstream_seal_pass),
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    state='PASS' if license_ack else 'BLOCKED'
    reason=None if license_ack else 'MARKET_DATA_LICENSE_ACK_REQUIRED'
    print(json.dumps({'state':state,'reason':reason,'output':str(a.output),'source_digest':digest,'license_ok':license_ack},sort_keys=True))
    return 0 if license_ack else 3
if __name__=='__main__':
    raise SystemExit(main())
