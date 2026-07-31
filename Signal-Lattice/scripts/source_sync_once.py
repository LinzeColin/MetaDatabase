#!/usr/bin/env python3
"""Compatibility entry: deterministic Git registry reconcile, not README-only download."""
from signal_lattice.cli import main
raise SystemExit(main(["reconcile-sources"]))
