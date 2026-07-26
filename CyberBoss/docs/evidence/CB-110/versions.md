# CB-110 Runtime Versions

- Implementation/release commit:
  `3cd8eee4f6b7c0a78f7b6fde90dae0f4ff1392fc`
- Target identity: SHA-256 prefix `7865f743d174`
- Node.js `24.18.0`
  - source:
    `https://nodejs.org/dist/v24.18.0/node-v24.18.0-linux-x64.tar.xz`
  - SHA-256:
    `55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742`
  - project command:
    `/opt/cyberboss-cloud/shared/toolchains/bin/node`
- SQLite adapter: `PASS` (`node:sqlite`, in-memory create/insert/select)
- Codex CLI `0.146.0-alpha.3.1`
  - main npm archive SHA-256:
    `3473d6d6416979b43118d203fa4e584c4e5af939206eee854d9db60c7555df17`
  - Linux x64 archive SHA-256:
    `d495bfa843ed9198327cc087b69b99aff09a66d4f5e7139137bc72d02ccf3e53`
  - project command:
    `/opt/cyberboss-cloud/shared/toolchains/bin/codex`
- App Server endpoint: `ws://127.0.0.1:8765`
  - `/readyz`: HTTP `200`
  - `initialize`: result present
  - `initialized`: sent
  - authenticated turn: not started
  - public reachability: false
- Codex home: `/var/lib/cyberboss/.codex`,
  `cyberboss:cyberboss:0700`
- Codex auth: `activation_pending`; `auth.json` absent, credential content
  reads=`0`
- Device-auth command is preserved in `version-manifest.json` but was not
  executed. It requires no public callback.
- Claude Code binary: `absent`
- Claude credential: `absent`
- Claude defaults:
  `CB_CLAUDE_RUNTIME=false`,
  `CB_CLAUDE_EVAL_PASSED=false`
- Business Runtime, WeChat activation, provider writes and
  Private-MetaDatabase writes: `0`
