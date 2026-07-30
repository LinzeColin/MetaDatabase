#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);a=p.parse_args()
 if not a.config.is_file():print(json.dumps({'state':'BLOCKED','reason':'INGRESS_CONFIG_MISSING'}));return 2
 text=a.config.read_text();find=[]
 if 'signal-lattice.linzezhang.com' not in text:find.append('DOMAIN_MISSING')
 if '127.0.0.1:8787' not in text and 'localhost:8787' not in text:find.append('LOOPBACK_ORIGIN_MISSING')
 if '0.0.0.0:8787' in text:find.append('PUBLIC_ORIGIN_FORBIDDEN')
 print(json.dumps({'state':'PASS' if not find else 'BLOCKED','findings':find}));return 0 if not find else 2
if __name__=='__main__':raise SystemExit(main())
