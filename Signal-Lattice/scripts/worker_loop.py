#!/usr/bin/env python3
from __future__ import annotations
import os,time
from pathlib import Path
from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.worker import run_once

def main():
 s=Settings.from_env(); db=RuntimeDB(s.state_dir/'runtime.db',Path(__file__).resolve().parents[1]/'db/schema.sql')
 worker=os.environ.get('SIGNAL_LATTICE_WORKER_ID','worker-1')
 while True:
  did=run_once(db,worker,s.worker_lease_seconds)
  time.sleep(0.2 if did else 2.0)
if __name__=='__main__':main()
