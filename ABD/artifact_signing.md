# ABD Artifact Signing Boundary

## Current local proof

This Phase records a Local SHA-256 attestation only in provenance.json. It
binds the frozen local source inputs, dependency locks, build-environment
observation, and companion policy documents to a canonical JSON payload.

That attestation is not a GPG, Sigstore, key-backed, identity-backed, or production release signature. AC-S14-P04 has not accessed a signing key, created a certificate, contacted a transparency log, or verified a remote artifact registry.

## Release boundary

The current P04 record is local pre-release evidence only. The source revision,
dependency evidence, and local build observation are recorded in
provenance.json; stage review and explicit approval evidence are required before any real release. A later authorized release gate must independently bind an immutable source revision, locked dependencies, a production-equivalent build environment, an authorized signing identity, and verification of the resulting signature.

No signing key, account credential, deployment target, or external service is accessed by this Phase.
