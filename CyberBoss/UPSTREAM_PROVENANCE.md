# Upstream Provenance and Separation Record

## Owner decision

The Owner selected A1 with an explicit separation requirement:

1. the `CyberBoss/` subtree remains AGPL-3.0-only;
2. historical source and copyright evidence are preserved;
3. the operational project is maintained only inside
   `LinzeColin/MetaDatabase/CyberBoss`;
4. no upstream remote, submodule, Git URL package dependency, automatic sync,
   runtime fetch, or periodic rebase may remain after the fixed import.

## Inputs verified during Prestage 0

| Input | Fixed identity | Purpose |
|---|---|---|
| CyberBoss | `WenXiaoWendy/cyberboss@373ab17d283f1e3b304a6a36e17e9e8d44f1acfc` | Historical code baseline |
| timeline-for-agent | `WenXiaoWendy/timeline-for-agent@62e1fa8db26f7a9147ad96579fc4077a39b94c8b` | Historical Timeline dependency baseline |
| TaskPack | SHA-256 `6ae91ee1f74b16e660f04d4d06cc744725cd97b9dc8d799c625186449fe3f178` | Product/acceptance baseline |
| Roadmap | SHA-256 `22a0ef56caab67c95357d60a3a725947f28a2744cecc79e66cacf638de1707b1` | Stage 0–5 roadmap baseline |
| AGPL license text | SHA-256 `526520455b0c01e09c1a23f6322a11d9e867de44dc833de8a94af6766dced64b` | Nested subtree license |

## Frozen source import completed by CB-000

Prestage 0 imported no application source. `CB-000` independently:

- reverified all three fixed commits, Git trees, manifests and licenses;
- imported ordinary-file bundles at `app/` and `vendor/`;
- replaced both moving Git dependencies with local `file:` packages;
- recorded 129 dependency entries, source/bundle hashes and exact modifications;
- proved `.git`, `.gitmodules`, remotes, branch dependencies, auto-sync and
  runtime source fetch are absent.

`whereabouts-mcp` has conflicting AGPL package metadata and GPLv3 license text.
The Owner selected strict dual-obligation compliance. Both original indicators
are retained and no upstream clarification was requested or received.

These frozen source records are legal and reproducibility evidence only. They
do not permit or configure future upstream synchronization.
