#!/usr/bin/env python3
from signal_lattice.cli import main
raise SystemExit(main(["ingest-skill-signal", *__import__("sys").argv[1:]]))
