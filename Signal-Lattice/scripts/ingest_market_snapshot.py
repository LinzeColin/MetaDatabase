#!/usr/bin/env python3
from signal_lattice.cli import main
raise SystemExit(main(["ingest-market-snapshot", *__import__("sys").argv[1:]]))
