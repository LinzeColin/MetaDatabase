# CB-130 Validation Report

- Run: `P1.4 / CB-130`
- Task state: `passed`
- CB-140: `not_started`
- Implementation/release:
  `81dc1ee211e554dd8b84001bfca4b8aa73bb89dd`
- Target: same pseudonymous authorized asset as CB-010/CB-100/CB-110/CB-120
- Real Codex adapter: `activation_pending`
- Real WeChat adapter: `activation_pending`
- Remote publication: `none`

## Result

The clean implementation commit produced an exact three-file artifact set:
complete Corresponding Source, its machine-readable manifest and SHA-256
checksums. Target check mode was write-free. Two applies and one independent
verify passed against the same commit; the first apply ran the complete App
suite with 170/170 passing and the second apply verified the existing immutable
candidate without rerunning tests.

The final staging process family contained exactly one supervisor, Runtime
simulator, channel simulator and bridge under one systemd cgroup. Runtime and
status listened only on `127.0.0.1:8765` and `127.0.0.1:8780`; the fixture
channel listened only on `127.0.0.1:19080`. Operator-host scans found neither
8765 nor 8780 publicly reachable.

Health and readiness were independently exercised: healthy/ready returned 200,
the forced-unready fixture remained healthy but returned ready 503, and the
protected status snapshot rejected missing and wrong authorization with 401.
The authorized bounded snapshot contained no PID, identity, thread, token,
message, prompt, result or absolute path.

Concurrent systemd start passed 100/100 with one process-family owner. All 100
independent lock contenders were denied while that owner held the singleton
lock. Actual SIGKILL/restart passed 100/100; every cycle observed down, a new
InvocationID, the ready predicate, one of each role and complete replacement of
the prior cgroup member set. Runtime, channel, bridge and whole-service fault
injection each observed down and recovered without a false-green result.

Final target state is disabled/inactive with MainPID 0, no CyberBoss process,
no 8765/8780/19080 listener, no transient systemd drop-in, no ephemeral status
token and an empty incoming area. `current` remains on CB-100 and the controlled
workspace remains clean at CB-120. Only the immutable CB-130 candidate and its
root-controlled simulator staging configuration/state remain.

## Preserved execution corrections

Four non-passing attempts are retained rather than rewritten as success:

1. The first transfer used the wrong assumed archive root and included macOS
   AppleDouble metadata. Artifact hashes passed, install never ran and the two
   exact incoming directories were removed before a strict three-file
   retransfer.
2. Target App tests passed 170/170, but Node 24 emitted the TAP summary with an
   information-symbol prefix while the initial parser accepted only a
   hash-prefix summary. No candidate was moved into place; cleanup passed. The
   parser now reads the stable `tests <integer>` fields independent of prefix.
3. The next candidate installed and verified, but systemd 255 rejected
   `kill-whom all` for auxiliary processes before restart cycle one. Cleanup
   returned the service to disabled/inactive with zero processes/listeners.
4. A line-level diagnostic rerun confirmed that exact command. The final
   implementation kills the systemd main process and relies on the already
   fixed `KillMode=control-group`, then proves that no prior cgroup member
   remains after recovery. The superseded candidate was removed only after its
   exact release manifest was checked; its attempt artifact made it
   recoverable during correction.

## Compliance and security boundary

Original App/vendor source, license files, notices and the unresolved
whereabouts conflict record are preserved. The conservative expression remains
`AGPL-3.0-only AND GPL-3.0-only`. There is no upstream remote, sync, support or
endorsement claim, and `upstream_clarification_received=false`.

P0/P1 findings, secret-value hits, non-loopback listeners, detached orphans,
duplicate owners, real credential operations, provider writes and
Private-MetaDatabase operations are all zero. Real Codex and WeChat were not
activated; their configuration-only switches remain `activation_pending`.
No target address, credential value, PID or private runtime content is stored
in this evidence.

## Acceptance

- AC-011: `passed`
- AC-040: `passed`
- AC-044: `passed`
- AC-062: `passed`
- Only CB-130 changed task state.
- CB-140 and every later task, plus PG-1–PG-5, remain `not_started`.
- No branch, PR, tag, release or push exists remotely.

The fail-closed repository validator result is recorded in `validation.txt`.
