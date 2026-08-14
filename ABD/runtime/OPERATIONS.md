# ABD Observation Runtime Operations Layer

This operational layer is separate from the frozen S18/P04 offline acceptance
artifacts. It manages only the deployed `OBSERVATION_ONLY` container and never
creates recommendations, submits orders, reads market or account data, accesses
TAB/Gmail, changes Cloudflare, or mutates financial facts.

## Scheduled local windows

- Daily: verifies the owned container is healthy and the bounded watchdog is enabled.
- Weekly: also verifies the retained local rollback image is available.
- Monthly: also rejects an unsafe watchdog restart-history path.

The three timers perform approximately 37 local checks per 31-day month and
make zero Cloudflare or R2 requests. A failed window produces only a local
systemd pause record (`PAUSE_CONTRACT_AND_ESCALATE_OWNER_OUTBOX_ONLY`); it does
not patch, back up, email, restore, change traffic, or restart the runtime.

## Rollback

Disable the three `abd-v0001-observation-operations-*.timer` units and remove
their matching local unit/script files. The running observation container and
the bounded S18/P03 watchdog remain independent of this operations layer.
