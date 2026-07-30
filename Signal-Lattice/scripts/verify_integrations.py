#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os
from pathlib import Path
REQUIRED={
 'private-database':['SIGNAL_LATTICE_PRIVATE_DB_CLIENT'],
 'object-storage':['SIGNAL_LATTICE_R2_PRIMARY_NAMESPACE','SIGNAL_LATTICE_R2_BACKUP_NAMESPACE','SIGNAL_LATTICE_OCI_BACKUP_TARGET'],
 'status':['SIGNAL_LATTICE_STATUS_SNAPSHOT'],
}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('kind',choices=sorted(REQUIRED));a=p.parse_args();missing=[]
 for key in REQUIRED[a.kind]:
  value=os.environ.get(key,'')
  if not value:missing.append(key)
  elif key.endswith(('_CLIENT','_SNAPSHOT')) and not Path(value).exists():missing.append(key+':PATH_NOT_FOUND')
 state='PASS' if not missing else 'BLOCKED'
 print(json.dumps({'state':state,'integration':a.kind,'missing':missing,'secret_values_emitted':False},sort_keys=True));return 0 if not missing else 2
if __name__=='__main__':raise SystemExit(main())
