# CB-140 Validation Report

- Run: `P1.5 / CB-140`
- Task state: `passed`
- Stage 1 task progress: `5/5`
- PG-1: `not_started`
- CB-200 and every later task: `not_started`
- Implementation/release:
  `571438751638a01c4648ff4fdf27403a97a971c3`
- Target: same pseudonymous authorized asset as CB-010 through CB-130
- Real Codex adapter: `activation_pending`
- Real WeChat adapter: `activation_pending`
- Remote publication: `none`

## Result

The clean implementation commit produced an exact three-file artifact set:
complete Corresponding Source, a machine-readable manifest and SHA-256
checksums. Target check mode was write-free. Two applies and one independent
verify passed against the same commit; the first apply ran the complete App
suite with 175/175 passing, and the second apply verified the existing
immutable candidate without rerunning tests.

The transient loopback process family then passed ten deterministic
channel-simulator → bridge → Runtime-simulator → confirmed-channel-delivery
round trips. Each successful trace contains the ordered inbound, Runtime,
outbox, delivery and canonical stages under one derived trace ID. The final
redacted trace contains 194 stage records across 34 trace IDs and no raw
message, result, sender, account, context token, thread or turn field.

The inbound allowlist rejected an unauthorized sender before Runtime with zero
Runtime calls. Exactly 32768 UTF-8 bytes produced one Runtime call; 32769 bytes
were rejected with zero Runtime calls. Twenty additional idle messages measured
P50 372 ms and P95 378 ms, below the 5 s and 10 s thresholds.

Operational source/config, cgroup process arguments, connections and listeners
had zero Mac dependency. The target exposed exactly three loopback listeners
during the acceptance window. An operator-host scanner first proved its SSH
baseline reachable, then found ports 8765, 8780 and 19080 unreachable in three
attempts each.

Final target state is disabled/inactive with no CyberBoss process, listener,
runtime drop-in, token, raw trace, staging state, staging environment or
incoming artifact. `current` remains on CB-100 and the controlled workspace
remains clean at CB-120. The exact immutable CB-140 candidate is retained but
is not active.

## Preserved execution corrections

Non-passing attempts are retained rather than rewritten as success:

1. The first prestage check after implementation failed only because the two
   integrity manifests still described the prior file set. Both manifests were
   regenerated after the implementation report stabilized, and the complete
   fail-closed prepare validator then passed twice.
2. The exact artifact builder passed, but the first local `shasum` verification
   inherited an unavailable `C.UTF-8` locale and stopped. Rechecking the same
   unmodified artifacts under `LC_ALL=C` passed.
3. Automated parsing initially selected an obsolete root login reference from
   the protected baseline record. Public-key authentication was rejected
   before any remote command. The canonical protected-record login field was
   then used with the same pinned key and strict known-host file.
4. Direct SCP could not traverse the root-managed incoming parent. No install
   ran. The same three files were streamed through privileged exact-path writes,
   locked root-owned/read-only and SHA-256 checked before installation.
5. The installed `gh release list` did not expose `targetCommitish`; the
   read-only check stopped. The official GitHub API returned that field and
   confirmed zero matching release, alongside zero branch, PR and tag.
6. The in-app browser blocked the local fixture `file://` URL and explicitly
   prohibited browser workarounds. The required PNG evidence is a disclosed
   deterministic static render of the accepted fixture strings, not a browser
   capture and not real WeChat evidence.

The pre-closure `--final` validator was also run deliberately and failed only
`closure_parent`, proving it would not accept evidence before the required
one-child closure commit existed. That expected fail-closed result is retained
in `validation.txt`; the authoritative pass is rerun from the clean closure
commit.

Every target-side attempt ended with the service disabled/inactive. All removed
staging/incoming material is recoverable from the exact local commit, artifact
manifest and retrieved redacted evidence.

## Compliance and security boundary

Original App/vendor source, license files, notices and the unresolved
whereabouts conflict record are preserved. The conservative expression remains
`AGPL-3.0-only AND GPL-3.0-only`. There is no upstream remote, sync, support or
endorsement claim, and `upstream_clarification_received=false`.

P0/P1 findings, secret-value hits, raw private-content hits, non-loopback
listeners/connections, Mac dependencies, real credential reads, provider
writes and Private-MetaDatabase operations are all zero. Real Codex and WeChat
were not activated. No target address or credential value is stored in this
evidence.

## Acceptance

- AC-001 simulator fallback: `passed`; real adapter:
  `activation_pending`.
- AC-010 Mac-offline simulator Oracle: `passed`; real WeChat/Codex E2E:
  `activation_pending`.
- AC-061 latency: `passed` (`20/20`, P50 372 ms, P95 378 ms).
- AC-002 unauthorized sender zero Runtime call: `passed`.
- AC-006 32768/32769-byte boundary: `passed`.
- Only CB-140 changes task state.
- PG-1 was not executed in this Run.
- CB-200 and every later task, plus PG-1–PG-5, remain `not_started`.
- No branch, PR, tag, release or push exists remotely.

The fail-closed repository validator result is recorded in `validation.txt`.
