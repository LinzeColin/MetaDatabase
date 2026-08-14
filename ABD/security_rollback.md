# ABD Security Rollback Boundary

## Local P04 rollback drill

If this local release candidate has a source hash mismatch, dependency lock mismatch, malformed local attestation, critical or high security finding, or an attempted unsigned or unapproved release transition, the deterministic local action is DISABLE_S14_P04_LOCAL_RELEASE_CANDIDATE.

The drill must then restore the last signed S14/P03 evidence baseline and preserve immutable local evidence and deterministic replay inputs before stopping at the release gate. The P03 evidence is a local signed receipt baseline, not a claim that a production artifact or runtime is installed.

## External boundary

No shell, host, Cloudflare, OVH, account, order, or deployment mutation is performed by this Phase. This document is a recovery contract and local drill record; it is not evidence that a host rollback was executed.

A real production rollback requires its own authorized release and operations gate. That later gate must identify the deployed artifact, approved recovery target, authorized operator, immutable evidence location, and externally verified outcome before it can claim a production recovery.
