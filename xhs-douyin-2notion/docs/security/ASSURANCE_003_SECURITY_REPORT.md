# Assurance003 Security Report

## Public aggregate

| Control | Result |
|---|---|
| Current source and fixture scan | finding count = 0 |
| SAST | critical/high = 0 |
| SBOM / license | 33 components; unknown licenses = 0 |
| Anonymous OSV | 33 dependencies; unresolved critical/high = 0; vulnerabilities = 0 |
| Candidate release artifact | deterministic; allowlist findings = 0; Runtime Data files = 0 |
| CSP | Host Permission = 0; remote resources = 0 |
| Media and SSRF | CDN persistence = 0; forbidden target successes = 0; local-file reads = 0 |
| Local Git history | credential/authenticated-remote aggregate hits = 0 |

## Method boundary

The acceptance runner creates an allowlisted temporary environment with global/system Git config, interactive auth,
and credential manager interaction disabled. It does not inherit authentication variables. The history scan releases
only a count for strict credential/authenticated-remote rules; it never emits matching lines or values.

Current source and candidate artifact scanning remains comprehensive for secret, private path and media URL patterns.
Any non-zero result is a release blocker and causes Fail Closed.

## Release boundary

This report is a CI-synth security decision, not a production deployment receipt. It authorizes only
`TSK.x2n.assurance.004`; direct MVP deploy/run/online smoke stays in `TSK.x2n.assurance.005`. Alpha, Beta, fixed
health observation and soak are not release gates.
