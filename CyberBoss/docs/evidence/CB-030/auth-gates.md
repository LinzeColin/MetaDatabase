# CB-030 Consolidated Codex + WeChat Activation Sheet

## Claim boundary

This sheet is prepared and syntax-reviewed; it was **not executed as an
activation** in P0.4. The authorized OVH staging probe found no Codex CLI,
`/var/lib/cyberboss/.codex/auth.json`, CyberBoss state directory or WeChat
account state. Therefore:

```text
Codex real adapter = activation_pending
WeChat real adapter = activation_pending
AC-001 real = activation_pending
AC-010 real = activation_pending
```

The local development Mac has the pinned `codex-cli
0.146.0-alpha.3.1`, an authenticated login status and an owner-only `0600`
auth file. This only proves local preparation; it does not satisfy the OVH-only
runtime or Mac-offline acceptance Oracle.

No auth/session file content, token, QR payload or private conversation was
read. No account ID, email, credential value or raw CLI output was emitted or
persisted; the login-status stdout was classified in memory and discarded.

## Preconditions

- Run only after the current immutable CyberBoss release and exact pinned
  Codex CLI are installed on the already-authorized OVH target.
- Dedicated user `cyberboss` and `/var/lib/cyberboss` must exist.
- Stop if the WeChat flow reports ban/risk-control or if any command would
  print credential content.
- Keep `CB_RUNTIME_PROVIDER=simulator` and
  `CB_CHANNEL_PROVIDER=simulator` until the corresponding verification block
  passes.

## One consolidated activation window

### 1. Prepare protected state

```bash
sudo install -d -o cyberboss -g cyberboss -m 0700 \
  /var/lib/cyberboss/.codex \
  /var/lib/cyberboss/accounts \
  /var/lib/cyberboss/auth-quarantine

sudo -u cyberboss -H env CODEX_HOME=/var/lib/cyberboss/.codex \
  codex --version
```

Oracle: output is exactly the version pinned by
`CyberBoss/machine/source-lock.json`. Do not continue on a different version.

### 2. Codex device auth — one browser confirmation

```bash
sudo -u cyberboss -H env CODEX_HOME=/var/lib/cyberboss/.codex \
  codex login --device-auth

sudo -u cyberboss -H env CODEX_HOME=/var/lib/cyberboss/.codex \
  codex login status

sudo test -r /var/lib/cyberboss/.codex/auth.json
sudo chmod 0600 /var/lib/cyberboss/.codex/auth.json
sudo chown cyberboss:cyberboss /var/lib/cyberboss/.codex/auth.json
sudo stat -c 'owner=%U group=%G mode=%a' \
  /var/lib/cyberboss/.codex/auth.json
```

Do not run `cat`, `jq`, `grep`, checksum or backup against `auth.json`.

### 3. Codex loopback probe

Start through the later systemd/release contract, or for a foreground staging
probe only:

```bash
sudo -u cyberboss -H env CODEX_HOME=/var/lib/cyberboss/.codex \
  codex app-server --listen ws://127.0.0.1:8765
```

From a second authorized shell:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8765/readyz
ss -lnt | awk '$4 ~ /127[.]0[.]0[.]1:8765$/ {found=1} END {exit !found}'
ss -lnt | awk '$4 ~ /(^|[^0-9])8765$/ && $4 !~ /127[.]0[.]0[.]1:8765$/ {bad=1} END {exit bad}'
```

The real Codex adapter remains `activation_pending` until an authenticated
thread/turn produces a completion artifact and the App Server is proven
loopback-only. Readiness alone is not authentication evidence.

### 4. WeChat QR — one scan

Use the immutable release command already defined by the operations contract:

```bash
sudo -u cyberboss -H env CYBERBOSS_STATE_DIR=/var/lib/cyberboss \
  bash -lc 'cd /opt/cyberboss-cloud/current && npm run login'
```

Scan only the QR shown by that exact local command. Do not copy the QR URL or
payload into chat, logs, screenshots or Git.

After confirmation:

```bash
sudo find /var/lib/cyberboss/accounts -maxdepth 1 -type f \
  -name '*.json' -exec chown cyberboss:cyberboss {} +
sudo find /var/lib/cyberboss/accounts -maxdepth 1 -type f \
  -name '*.json' -exec chmod 0600 {} +
sudo find /var/lib/cyberboss/accounts -maxdepth 1 -type f \
  -name '*.json' -printf '%m\n' | sort -u
```

The last command may print modes only. It must not print filenames or content.

### 5. Harmless real channel Oracle

1. Keep one authorized staging user in the protected allowlist.
2. Send `ping` from that WeChat account.
3. Require one received source message ID, one candidate cursor, one adapter
   send call and one provider-confirmed text receipt.
4. Require the visible reply `pong`.
5. Save only a screenshot with account/avatar/notification identifiers
   redacted and a structured log containing hashes/counts/statuses, never raw
   IDs, context token, bearer or chat history.

Only this flow can move the WeChat adapter from `activation_pending` to
`verified`. The P0.4 screenshot is a clearly marked simulator fixture and
cannot do so.

### 6. Switch independently

After each adapter passes its own Oracle, change only that provider:

```dotenv
CB_RUNTIME_PROVIDER=codex
CB_CHANNEL_PROVIDER=weixin
```

Never switch an adapter because the other one passed. AC-010 additionally
requires ten real OVH E2E results while the Mac is offline; it remains pending
until that later gate runs.

## Re-login and revocation

### Codex

```bash
sudo systemctl stop cyberboss-cloud.service
sudo -u cyberboss -H env CODEX_HOME=/var/lib/cyberboss/.codex codex logout
sudo -u cyberboss -H env CODEX_HOME=/var/lib/cyberboss/.codex \
  codex login --device-auth
sudo chmod 0600 /var/lib/cyberboss/.codex/auth.json
```

Re-run login status, exact-version, loopback and one harmless completion Oracle
before restarting the real adapter.

### WeChat

```bash
sudo systemctl stop cyberboss-cloud.service
sudo mv /var/lib/cyberboss/accounts \
  /var/lib/cyberboss/auth-quarantine/wechat-<UTC_TIMESTAMP>
sudo install -d -o cyberboss -g cyberboss -m 0700 \
  /var/lib/cyberboss/accounts
sudo -u cyberboss -H env CYBERBOSS_STATE_DIR=/var/lib/cyberboss \
  bash -lc 'cd /opt/cyberboss-cloud/current && npm run login'
```

Use a real UTC timestamp in the placeholder. Keep the quarantined directory
root-only until incident review; do not commit, upload or print it. On
ban/risk-control, stop here and mark only WeChat `failed`; do not retry through
unofficial bypasses.

## Evidence to retain

- exact CLI version and exit status;
- auth/state presence plus owner/mode booleans;
- App Server loopback/readiness result;
- redacted real adapter classification;
- redacted WeChat screenshot only after real activation;
- no raw stdout/stderr from login commands.
