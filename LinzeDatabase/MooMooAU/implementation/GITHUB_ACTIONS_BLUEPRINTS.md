# GitHub Actions Blueprints

以下为实现约束，不是可直接使用的生产 Secret 配置。

## Ingest

```yaml
name: moomooau-ingest
on:
  schedule:
    - cron: '30 4 * * *'
      timezone: 'Australia/Sydney'
  workflow_dispatch:
    inputs:
      mode:
        type: choice
        options: [incremental, full-reconcile, raw-only]
        default: incremental
permissions:
  contents: read
concurrency:
  group: moomooau-production
  cancel-in-progress: false
jobs:
  ingest:
    runs-on: ubuntu-latest
    environment: moomooau-production
    timeout-minutes: 45
    steps:
      - checkout public code at immutable ref
      - verify pinned actions and package
      - run container by fixed digest
      - create tmpfs and disable core dumps/debug tracing
      - obtain Gmail access token from protected refresh token
      - obtain repository-scoped GitHub App installation token
      - run deterministic pipeline
      - validate remote recovery and exact message mutation
      - publish redacted evidence only after private success
      - always cleanup tmpfs and revoke ephemeral state
```

Sunday behavior is computed inside the deterministic runner from `Australia/Sydney` local date; no second scheduled Workflow.
`timezone` 负责 DST 感知的 04:30 本地调度目标。GitHub 官方明确说明 schedule 可能排队延迟或被丢弃，
因此实际启动时间必须进入新鲜度 Evidence，后续运行按 Gmail History 水位幂等补偿，周日再执行 Full Reconciliation；不得把 04:30 描述为精确启动 SLA。

## CI

```yaml
on: [pull_request, push]
permissions:
  contents: read
jobs:
  quality:
    # no production secrets; synthetic fixtures only
  security:
    # CodeQL, dependency review, secret scan, action-SHA check, SBOM
  contracts:
    # dual-plane, requirements, AC, DAG, traceability, public redaction
```

## Reprocess

Protected `workflow_dispatch`; reads existing encrypted Raw, decrypts in tmpfs, runs selected Parser version, writes new Processed version, does not touch Gmail and does not overwrite Raw.

## Recovery Drill

Protected manual/quarterly Workflow; randomly samples encrypted EML/Processed/Timeline, uses Recovery Identity, verifies digests, emits only redacted Evidence. No full data download Artifact.

## Workflow Security

- No `pull_request_target` with untrusted code and Secrets；
- No self-hosted runner；
- No sensitive Artifact/Cache；
- Third-party Actions pinned to full SHA；
- `set -x` prohibited；
- logs use structured allowlisted fields；
- egress limited to Gmail API, GitHub API and required package endpoints at build time only；
- production container prebuilt, not dynamically installing floating dependencies。
