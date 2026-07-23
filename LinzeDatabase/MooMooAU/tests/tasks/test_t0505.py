from __future__ import annotations

import io
from dataclasses import replace
from datetime import date

from PIL import Image
from stage5_support import recovery_context, timeline_event

from moomooau_archive.m3 import M3State
from moomooau_archive.timeline_render import DeterministicTimelineRenderer


def test_t0505_fixed_renderer_is_byte_deterministic_and_order_independent() -> None:
    with (
        recovery_context() as first_context,
        recovery_context(safe_deferred=True) as second_context,
    ):
        first = timeline_event(first_context)
        second = timeline_event(second_context, statement_date=date(2026, 1, 1))
        renderer = DeterministicTimelineRenderer()
        snapshot = "a" * 64
        one = renderer.render((first, second), snapshot)
        two = renderer.render((second, first), snapshot)
        three = renderer.render((first, second), snapshot)
        assert one.png == two.png == three.png
        assert one.timeline_plaintext_sha256 == two.timeline_plaintext_sha256
        assert one.event_count == 2
        with Image.open(io.BytesIO(one.png)) as image:
            assert image.size == (1200, 720)
            assert image.info == {}


def test_t0505_semantic_event_change_changes_plaintext_digest_not_ciphertext_oracles() -> None:
    with recovery_context() as context:
        event = timeline_event(context)
        changed = replace(event, m3_state=M3State.UNKNOWN)
        renderer = DeterministicTimelineRenderer()
        first = renderer.render((event,), "b" * 64)
        second = renderer.render((changed,), "c" * 64)
        assert first.timeline_plaintext_sha256 != second.timeline_plaintext_sha256
        assert first.png != second.png
