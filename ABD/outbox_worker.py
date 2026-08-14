"""S18/P03 command-line wrapper for local-only owner outbox projection."""

from __future__ import annotations

from abd_acceptance.limited_self_heal import outbox_main


if __name__ == "__main__":
    raise SystemExit(outbox_main())
