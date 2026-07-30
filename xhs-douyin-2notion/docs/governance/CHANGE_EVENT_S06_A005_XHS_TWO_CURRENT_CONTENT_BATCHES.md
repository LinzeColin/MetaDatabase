# A005 Scope Change Event — Two Xiaohongshu Current-Content Batches

- Change event: `CE-X2N-20260729-S06-A005-XHS-TWO-CURRENT-BATCHES`
- Task: `TSK.x2n.assurance.005 / PH.X2N.6.5`
- Authorization basis: Owner direct authorization for the MVP scope replacement.
- Status: active only for the direct Owner MVP; historical adapter evidence remains unchanged.

## Superseded live A005 range

The previous direct-MVP Xiaohongshu favorites range is replaced by a second current-content range. This does not alter
the historical `xiaohongshu_favorites` adapter or CI fixtures.

| Range | Scope ID | Relation | Bounded execution |
|---|---|---|---|
| Xiaohongshu current content batch 1 | `xiaohongshu_current_content` | `saved_current` | 20 separately opened canonical detail pages |
| Xiaohongshu current content batch 2 | `xiaohongshu_current_content_second_batch` | `saved_current` | 20 separately opened canonical detail pages, strictly disjoint from batch 1 |
| Douyin favorites | `douyin_favorites` | `saved` | one explicit Owner-private visible-DOM Sidecar action |
| Douyin likes | `douyin_likes` | `liked` | one explicit Owner-private visible-DOM Sidecar action |

Both Xiaohongshu batches require an explicit Side Panel button per detail page. Before arm they retain only their
stable content-ID SHA-256 values in the private enrollment state; after arm each first Canonical write must match the
selected batch before the write. Neither path may scroll, paginate, navigate, retry, alter account state, create a
category, or persist a platform URL, raw media, credential, cookie, title, or DOM archive.

## Acceptance delta

- The private release input contains exactly four ordered manifests of 20 hashes each.
- The two Xiaohongshu manifests have an empty intersection before input freeze, before arm, and during capture-state
  validation.
- Each batch creates exactly one aggregate scope receipt only after 20 successful explicit captures.
- The baseline remains exactly 80 relations and fails closed if either current-content batch has fewer than 20
  matched Canonical records.

## Rollback

The change is source-only until real Owner input is frozen. Before deployment, reverting this event and its matching
source change returns the release contract to the prior live range with no Canonical or platform side effects.
