from pathlib import Path

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountConnectRequest, AccountSyncRequest
from social_archive.registry import ConnectorRegistry

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"
PWA = ROOT / "apps/pwa/app.js"


def _run(settings, store, service):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="xiaohongshu",
        auth_method="browser_session",
        display_name="我的小红书",
        relation_types=["favorite", "like"],
    ))
    account_id = coordinator.complete_connection(
        platform="xiaohongshu",
        auth_method="browser_session",
        connection_ref=start.connection_ref,
        external_account_id="owner-control",
        display_name="我的小红书",
        auto_sync_enabled=True,
        sync_interval_minutes=360,
        metadata={"source": "control-test"},
        verified=True,
    )
    run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["favorite", "like"], trigger_type="manual"
    ))
    return account_id, run["sync_run_id"]


def test_runtime_store_supports_pause_resume_and_cancel(settings, store, service):
    _account_id, run_id = _run(settings, store, service)
    assert store.control_sync_run(run_id, "pause")
    assert store.get_sync_run(run_id)["status"] == "paused"
    assert store.control_sync_run(run_id, "resume")
    assert store.get_sync_run(run_id)["status"] == "queued"
    assert store.control_sync_run(run_id, "cancel")
    assert store.get_sync_run(run_id)["status"] == "cancelled"
    assert not store.control_sync_run(run_id, "resume")


def test_retry_is_limited_to_retryable_terminal_states(settings, store, service):
    _account_id, run_id = _run(settings, store, service)
    store.update_sync_run(run_id, status="failed", error_code="TEST", error_message="fixture")
    assert store.control_sync_run(run_id, "retry")
    row = store.get_sync_run(run_id)
    assert row["status"] == "queued"
    assert row["last_error_code"] is None
    assert row["last_error_message"] is None


def test_extension_and_pwa_expose_cooperative_sync_controls():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    bridge = (EXT / "bridge.js").read_text(encoding="utf-8")
    content = (EXT / "content/account-mirror.js").read_text(encoding="utf-8")
    sidepanel = (EXT / "sidepanel.js").read_text(encoding="utf-8")
    sidepanel_html = (EXT / "sidepanel.html").read_text(encoding="utf-8")
    pwa = PWA.read_text(encoding="utf-8")

    for token in (
        "SYNC_CONTROL_KEY", "controlSyncRun", "removeQueuedSync",
        "broadcastMirrorControl", "SA_GET_SYNC_CONTROL_STATE",
    ):
        assert token in background
    assert 'message.type === "SA_CONTROL_SYNC_RUN"' in bridge
    assert 'message?.type === "SA_MIRROR_CONTROL"' in content
    assert "readScanControl" in content
    assert 'postToExtension("SA_CONTROL_SYNC_RUN"' in pwa
    assert 'type: "SA_CONTROL_SYNC_RUN"' in sidepanel
    for css_class in ('class="pause"', 'class="resume"', 'class="cancel"'):
        assert css_class in sidepanel_html


def test_pause_and_cancel_are_not_just_visual_labels():
    background = (EXT / "background.js").read_text(encoding="utf-8")
    content = (EXT / "content/account-mirror.js").read_text(encoding="utf-8")
    assert 'await SA.api(`/v1/sync-runs/${encodeURIComponent(syncRunId)}/control`' in background
    assert 'await removeQueuedSync({ syncRunId, accountId: effectiveAccountId })' in background
    assert 'return controlledResult(platform, relationType, control)' in content
    assert 'if (relationResult?.controlled) break' in background


def test_abandoned_browser_sync_runs_are_reaped_instead_of_showing_syncing_forever(store):
    # A browser scan is owned by the extension's MV3 service worker, which
    # Chrome can terminate at any moment. Nothing then moves the run out of its
    # active state, so it sat in "scanning" forever and the UI kept advertising
    # "syncing" for work that had already died -- indistinguishable from slow
    # progress for a non-technical Owner.
    import time as _time

    account_id = store.upsert_source_account(
        platform="xiaohongshu", external_account_id="https://www.xiaohongshu.com/user/profile/abc",
        display_name="我", auth_method="browser_session", auth_handle_ref=None,
        connection_state="connected",
    )
    stuck = store.create_sync_run(
        source_account_id=account_id, platform="xiaohongshu", mode="first_full",
        relation_types=["favorite"], trigger_type="manual",
    )
    store.update_sync_run(stuck, status="scanning")

    # Still fresh: a slow scan must not be killed.
    assert store.reap_stale_sync_runs() == 0
    assert store.get_sync_run(stuck)["status"] == "scanning"

    reaped = store.reap_stale_sync_runs(now=_time.time() + store.STALE_SYNC_RUN_AFTER_SECONDS + 60)
    assert reaped == 1
    row = store.get_sync_run(stuck)
    assert row["status"] == "failed"
    assert row["last_error_code"] == "SYNC_RUN_ABANDONED"
    assert "再点一次" in (row["last_error_message"] or "")


def test_a_paused_run_is_never_reaped(store):
    # Pausing is a deliberate Owner action, not an abandoned worker.
    import time as _time

    account_id = store.upsert_source_account(
        platform="douyin", external_account_id="https://www.douyin.com/user/self",
        display_name="我的", auth_method="browser_session", auth_handle_ref=None,
        connection_state="connected",
    )
    run = store.create_sync_run(
        source_account_id=account_id, platform="douyin", mode="first_full",
        relation_types=["favorite"], trigger_type="manual",
    )
    store.update_sync_run(run, status="paused")
    assert store.reap_stale_sync_runs(now=_time.time() + store.STALE_SYNC_RUN_AFTER_SECONDS + 3600) == 0
    assert store.get_sync_run(run)["status"] == "paused"
