from __future__ import annotations
import json
from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.exports import StandardExporter

def main() -> int:
    settings=Settings.from_env(); settings.ensure_directories(); store=RuntimeStore(settings.runtime_db); store.initialize()
    print(json.dumps(StandardExporter(store, settings.export_root).export_all(),ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
