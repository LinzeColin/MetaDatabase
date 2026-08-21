# DSH Desktop local normal-app bridge

This bridge keeps the official stable release service and download flow, while making macOS installation a normal click-through update.

- The downloaded upstream app is checked before local personalization is applied.
- `~/.dsh` and `~/.harness-ui` are never replaced by the installer.
- The custom icon lives at `~/.dsh/personalization/dsh-desktop/icon.icns`.
- The previous `.app` remains under `~/.dsh/desktop-updates/rollback/`.
- A machine-readable result is written to `~/.dsh/desktop-updates/last-update.json`.
- If a future upstream runtime no longer matches the patch contract, installation stops before replacing the current app.
- The native app menu exposes the upstream check/download action. `Cmd+W` closes the window while the local runtime stays available; `Cmd+Q` exits DSH and releases its runtime port.
- HarnessUI catalog/state changes are consumed without restarting DSH, and “同步素材” requests an immediate catalog refresh.
- Failed staging directories are removed automatically; the current app is reopened and the failure receipt remains available.

The local app is ad-hoc signed after personalization. A public signed build should include the external-icon and updater bridge in source before Developer ID signing and notarization.
