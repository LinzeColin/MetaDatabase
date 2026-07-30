#!/usr/bin/env python3
from signal_lattice.cli import main
raise SystemExit(main(["calibrate", *__import__("sys").argv[1:]]))
