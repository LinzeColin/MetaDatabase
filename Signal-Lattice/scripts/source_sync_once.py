#!/usr/bin/env python3
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from signal_lattice.util import atomic_write

def main():
 out=Path(os.environ.get('SIGNAL_LATTICE_ARTIFACT_DIR','/var/lib/signal-lattice/artifacts'))/'source_sync.json'
 receipt={'state':'DEGRADED','reason':'RUNTIME_SOURCE_BINDING_REQUIRED','observed_at':datetime.now(timezone.utc).isoformat(),'upstream_write_allowed':False,'runtime_agent_dependency':0,'runtime_llm_tokens':0}
 atomic_write(out,json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True).encode())
if __name__=='__main__':main()
