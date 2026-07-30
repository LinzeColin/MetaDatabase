# Third-Party Boundary

Social Archive does not vendor or copy third-party source into its first-party transaction core. Current direct Python dependencies are declared in `pyproject.toml` and resolved in `uv.lock`; the lockfile is the version source for this product revision.

Optional readers, downloaders and archival systems must remain behind an isolated process, CLI, HTTP, container or file-import boundary. Before any such integration is enabled, the owning Task must bind its version, license, provenance, secret scope, output contract and failure behavior. GPL/AGPL code must not enter the first-party core.

No entry in this document authorizes real-account access, platform requests, destination writes, dependency-source copying or deployment.
