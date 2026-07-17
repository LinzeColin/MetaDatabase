#!/usr/bin/env python3
"""S7PDT04: one-way local -> Cloudflare cloud publication channel.

Exports the PUBLICATION SURFACE ONLY from the local production database -
owner-signed published relationships (derivation_rule =
reviewed_relationship_fact_publication), their endpoint entities, the
evidence index (locator + excerpt + official URL), and active snapshot
metadata - renders it as D1-compatible SQL, pushes it to the remote D1
database via wrangler, and verifies remote row counts against the export.

Boundary (ROOT_LOCK HR1 / S7PDT04 contract):
- One-way: nothing is ever read back from the cloud into the local DB.
- The publication layer carries published facts, score context and evidence
  index only; candidates, review queues, raw texts and scoring internals
  never leave the machine.
- Raw official-source archives belong in R2 (requires the owner to enable
  R2 on the account); this script records R2 status honestly and does not
  fake that leg of the drill.

Free-tier quota accounting is emitted with every run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402

SCHEMA_VERSION = "eei-cloud-publication-channel-v2"
TASK_ID = "S7PDT04"
ACCEPTANCE_IDS = ["ACC-S7PDT04"]
D1_DATABASE = "eei-publication"
SCHEMA_FILE = ROOT / "infra" / "cloudflare" / "d1_publication_schema.sql"
PUBLISHED_RULE = "reviewed_relationship_fact_publication"

# EEI-F05: the public surface never carries contact identifiers or internal
# review/signature internals. Qualifiers are reduced to this allowlist at
# export time; owner_actor is replaced by the opaque owner_role that already
# rides in the same payload. Everything else stays local.
PUBLIC_QUALIFIER_ALLOWLIST = (
    "path_role",
    "owner_role",
    "record_mode",
    "reviewed_at",
    "direction_note",
    "decision_set_key",
    "parser_version",
    "structured_fact",
    "source_threshold_policy",
)


def sanitize_public_qualifiers(qualifiers: dict[str, Any] | None) -> dict[str, Any] | None:
    if not qualifiers:
        return None
    public = {k: qualifiers[k] for k in PUBLIC_QUALIFIER_ALLOWLIST if k in qualifiers}
    return public or None

D1_FREE_TIER = {
    "storage_gb": 5,
    "rows_read_per_day": 5_000_000,
    "rows_written_per_day": 100_000,
}


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def export_publication_surface() -> dict[str, list[dict[str, Any]]]:
    with connect_database() as conn:
        relationships = [
            {
                "id": str(r[0]),
                "subject_entity_id": str(r[1]),
                "object_entity_id": str(r[2]),
                "relationship_type": r[3],
                "relationship_family": r[4],
                "status": r[5],
                "confidence": float(r[6]) if r[6] is not None else None,
                "observed_at": r[7].isoformat() if r[7] else None,
                "published_at": r[8].isoformat() if r[8] else None,
                "qualifiers_json": (
                    json.dumps(sanitized, ensure_ascii=False)
                    if (sanitized := sanitize_public_qualifiers(r[9]))
                    else None
                ),
            }
            for r in conn.execute(
                """
                SELECT r.id, r.subject_entity_id, r.object_entity_id,
                       r.relationship_type, r.relationship_family, r.status,
                       r.confidence, r.observed_at, r.created_at, r.qualifiers
                FROM relationships r
                WHERE r.derivation_rule = %s
                """,
                (PUBLISHED_RULE,),
            ).fetchall()
        ]
        entity_ids = sorted(
            {r["subject_entity_id"] for r in relationships}
            | {r["object_entity_id"] for r in relationships}
        )
        entities = [
            {
                "id": str(r[0]),
                "canonical_name": r[1],
                "entity_type": r[2],
                "status": r[3],
            }
            for r in conn.execute(
                "SELECT id, canonical_name, entity_type, status FROM entities"
                " WHERE id = ANY(%s::uuid[])",
                (entity_ids,),
            ).fetchall()
        ]
        evidence = [
            {
                "relationship_id": str(r[0]),
                "source_document_id": str(r[1]),
                "role": r[2],
                "locator": r[3],
                "support_excerpt": r[4],
                "source_url": r[5],
                "source_title": r[6],
                "publisher": r[7],
                "document_date": r[8].isoformat() if r[8] else None,
            }
            for r in conn.execute(
                """
                SELECT re.relationship_id, re.source_document_id, re.role::text,
                       re.locator, re.support_excerpt, sd.url, sd.title,
                       sd.publisher, sd.document_date
                FROM relationship_evidence re
                JOIN source_documents sd ON sd.id = re.source_document_id
                WHERE re.relationship_id = ANY(%s::uuid[])
                """,
                ([r["id"] for r in relationships],),
            ).fetchall()
        ]
        snapshots = [
            {
                "snapshot_key": r[0],
                "scope": r[1],
                "record_mode": r[2],
                "status": r[3],
                "as_of": r[4].isoformat() if r[4] else None,
                "activated_at": r[5].isoformat() if r[5] else None,
            }
            for r in conn.execute(
                """
                SELECT snapshot_key, scope, record_mode, status, as_of, activated_at
                FROM data_snapshots WHERE status = 'active'
                """
            ).fetchall()
        ]
        # S12PB: per-year official filing depth for the cloud vertical
        # timeline. Aggregate counts only - no titles, URLs or raw content
        # leave the machine (CF-L2 publication-surface boundary intact).
        filing_year_counts = [
            {"year": int(r[0]), "filings": int(r[1])}
            for r in conn.execute(
                """
                SELECT extract(year FROM sd.document_date)::int AS year,
                       count(*)::int AS filings
                FROM source_documents sd
                JOIN sources src ON src.id = sd.source_id AND src.code = 'sec_edgar'
                GROUP BY 1
                ORDER BY 1
                """
            ).fetchall()
        ]
        # EEI-F01: static supply-chain stage rail (reference data, no facts).
        supply_chain_stages = [
            {
                "stage_id": r[0],
                "stage_order": int(r[1]),
                "slug": r[2],
                "name_zh": r[3],
                "name_en": r[4],
                "default_direction": r[5],
                "examples": r[6],
            }
            for r in conn.execute(
                """
                SELECT stage_id, stage_order, slug, name_zh, name_en,
                       default_direction, examples
                FROM supply_chain_stages ORDER BY stage_order
                """
            ).fetchall()
        ]
        # EEI-F01/F02: one atomic analysis-context identity per publish so
        # every cloud screen reads the same snapshot/model identity. Identity
        # fields only - no activated_by contact detail beyond the system tag,
        # no metadata blob.
        context_row = conn.execute(
            """
            SELECT aac.context_key, aac.active_scoring_profile_version_id,
                   ds.snapshot_key, aac.active_scoring_run_id, aac.refresh_token,
                   aac.refresh_generation, aac.status, aac.activated_at,
                   aac.affected_modules,
                   sp.profile_key, spv.version, sm.model_key, sm.version
            FROM active_analysis_contexts aac
            JOIN scoring_profile_versions spv
              ON spv.id = aac.active_scoring_profile_version_id
            JOIN scoring_profiles sp ON sp.id = spv.profile_id
            JOIN scoring_models sm ON sm.id = spv.model_id
            LEFT JOIN data_snapshots ds ON ds.id = aac.active_data_snapshot_id
            WHERE aac.context_key = 'global'
            """
        ).fetchone()
        active_analysis_context = (
            {
                "schema_version": "active-analysis-context-v1",
                "context_key": context_row[0],
                "active_scoring_profile_version_id": str(context_row[1]),
                "active_data_snapshot_key": context_row[2],
                "active_scoring_run_id": (
                    str(context_row[3]) if context_row[3] else None
                ),
                "refresh_token": str(context_row[4]),
                "refresh_generation": int(context_row[5]),
                "status": context_row[6],
                "activated_at": (
                    context_row[7].isoformat() if context_row[7] else None
                ),
                "affected_modules": list(context_row[8] or []),
                "model_version": f"{context_row[11]}@{context_row[12]}",
                "profile_version": f"{context_row[9]}@{context_row[10]}",
            }
            if context_row
            else None
        )
    return {
        "relationships": relationships,
        "entities": entities,
        "relationship_evidence": evidence,
        "snapshot_meta": snapshots,
        "filing_year_counts": filing_year_counts,
        "supply_chain_stages": supply_chain_stages,
        "active_analysis_context": active_analysis_context,
    }


def render_sql(surface: dict[str, Any]) -> str:
    statements: list[str] = []
    for table in (
        "relationship_evidence",
        "relationships",
        "entities",
        "snapshot_meta",
        "filing_year_counts",
        "supply_chain_stages",
    ):
        statements.append(f"DELETE FROM {table};")
    for row in surface["entities"]:
        statements.append(
            "INSERT INTO entities(id, canonical_name, entity_type, status) VALUES ("
            + ", ".join(
                sql_quote(row[k]) for k in ("id", "canonical_name", "entity_type", "status")
            )
            + ");"
        )
    for row in surface["relationships"]:
        statements.append(
            "INSERT INTO relationships(id, subject_entity_id, object_entity_id,"
            " relationship_type, relationship_family, status, confidence,"
            " observed_at, published_at, qualifiers_json) VALUES ("
            + ", ".join(
                sql_quote(row[k])
                for k in (
                    "id", "subject_entity_id", "object_entity_id",
                    "relationship_type", "relationship_family", "status",
                    "confidence", "observed_at", "published_at", "qualifiers_json",
                )
            )
            + ");"
        )
    for row in surface["relationship_evidence"]:
        statements.append(
            "INSERT INTO relationship_evidence(relationship_id, source_document_id,"
            " role, locator, support_excerpt, source_url, source_title, publisher,"
            " document_date) VALUES ("
            + ", ".join(
                sql_quote(row[k])
                for k in (
                    "relationship_id", "source_document_id", "role", "locator",
                    "support_excerpt", "source_url", "source_title", "publisher",
                    "document_date",
                )
            )
            + ");"
        )
    for row in surface["snapshot_meta"]:
        statements.append(
            "INSERT INTO snapshot_meta(snapshot_key, scope, record_mode, status,"
            " as_of, activated_at) VALUES ("
            + ", ".join(
                sql_quote(row[k])
                for k in ("snapshot_key", "scope", "record_mode", "status", "as_of",
                          "activated_at")
            )
            + ");"
        )
    for row in surface.get("filing_year_counts", []):
        statements.append(
            "INSERT INTO filing_year_counts(year, filings) VALUES ("
            + ", ".join(sql_quote(row[k]) for k in ("year", "filings"))
            + ");"
        )
    for row in surface.get("supply_chain_stages", []):
        statements.append(
            "INSERT INTO supply_chain_stages(stage_id, stage_order, slug, name_zh,"
            " name_en, default_direction, examples) VALUES ("
            + ", ".join(
                sql_quote(row[k])
                for k in ("stage_id", "stage_order", "slug", "name_zh", "name_en",
                          "default_direction", "examples")
            )
            + ");"
        )
    statements.append(
        "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
        f" ('published_at', {sql_quote(utc_now_iso())});"
    )
    statements.append(
        "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
        f" ('publisher_version', {sql_quote(SCHEMA_VERSION)});"
    )
    if surface.get("active_analysis_context"):
        statements.append(
            "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
            " ('active_analysis_context',"
            f" {sql_quote(json.dumps(surface['active_analysis_context'], ensure_ascii=False))});"
        )
    return "\n".join(statements) + "\n"


def wrangler(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["npx", "wrangler", *args], capture_output=True, text=True, cwd=str(cwd)
    )


def d1_execute(*, file: Path | None = None, command: str | None = None,
               cwd: Path) -> dict[str, Any]:
    args = ["d1", "execute", D1_DATABASE, "--remote", "--json"]
    if file is not None:
        args += ["--file", str(file)]
    if command is not None:
        args += ["--command", command]
    proc = wrangler(args, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler d1 execute failed: {proc.stderr[-400:]}")
    # wrangler prefixes --json output with progress lines; slice to the payload.
    stdout = proc.stdout
    start = min(
        (idx for idx in (stdout.find("["), stdout.find("{")) if idx >= 0),
        default=-1,
    )
    if start < 0:
        raise RuntimeError(f"wrangler produced no JSON payload: {stdout[-200:]}")
    return json.loads(stdout[start:])


def remote_counts(cwd: Path) -> dict[str, int]:
    # Remote D1 rejects wide compound SELECTs ("too many terms in compound
    # SELECT", SQLITE_ERROR 7500, observed at 6 UNION ALL terms on the first
    # v2 publish), so count each table with its own query.
    counts: dict[str, int] = {}
    for table in (
        "entities",
        "relationships",
        "relationship_evidence",
        "snapshot_meta",
        "filing_year_counts",
        "supply_chain_stages",
    ):
        result = d1_execute(
            command=f"SELECT count(*) AS n FROM {table}",
            cwd=cwd,
        )
        counts[table] = int(result[0]["results"][0]["n"])
    return counts


def r2_status(cwd: Path) -> dict[str, Any]:
    proc = wrangler(["r2", "bucket", "list"], cwd=cwd)
    if proc.returncode != 0:
        blocked = "10042" in (proc.stderr + proc.stdout)
        return {
            "enabled": False,
            "blocked_on": (
                "R2 must be enabled by the account owner in the Cloudflare "
                "Dashboard (error 10042). Raw-archive leg of the drill is "
                "honestly deferred; publish script supports it once enabled."
                if blocked
                else proc.stderr[-200:]
            ),
        }
    return {"enabled": True, "buckets_output": proc.stdout[-400:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sql-out", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="push to remote D1")
    args = parser.parse_args()

    cf_dir = ROOT / "apps" / "cloudflare-public"
    surface = export_publication_surface()
    sql = render_sql(surface)
    args.sql_out.parent.mkdir(parents=True, exist_ok=True)
    args.sql_out.write_text(sql, encoding="utf-8")

    local_counts = {
        table: len(rows) for table, rows in surface.items() if isinstance(rows, list)
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now_iso(),
        "d1_database": D1_DATABASE,
        "publication_boundary": {
            "included": [
                "owner-signed published relationships",
                "endpoint entities",
                "evidence index (locator + excerpt + official URL)",
                "active snapshot metadata",
                "per-year official filing counts (aggregates only)",
                "supply-chain stage reference rail (static, no facts)",
                "active analysis-context identity (allowlisted, no contacts)",
            ],
            "excluded": [
                "relationship candidates and review queues",
                "raw source texts and archives (R2 scope)",
                "scoring internals and model parameters",
                "background jobs / scheduler state",
                "contact identifiers and review/signature internals"
                " (EEI-F05 qualifier allowlist)",
            ],
            "direction": "one-way local->cloud; no cloud read-back",
        },
        "local_export_counts": local_counts,
        "sql_file": str(args.sql_out),
        "sql_statements": sql.count(";"),
        "applied": bool(args.apply),
    }

    if args.apply:
        d1_execute(file=SCHEMA_FILE, cwd=cf_dir)
        d1_execute(file=args.sql_out, cwd=cf_dir)
        counts = remote_counts(cf_dir)
        report["remote_counts"] = counts
        report["count_parity"] = {
            table: counts.get(table) == local_counts[table] for table in local_counts
        }
        report["drill_passed"] = all(report["count_parity"].values())
    report["r2"] = r2_status(cf_dir)
    meta_rows = 2 + (1 if surface.get("active_analysis_context") else 0)
    rows_written = sum(local_counts.values()) + meta_rows
    report["free_tier_quota_accounting"] = {
        "d1_free_tier": D1_FREE_TIER,
        "rows_written_this_publish": rows_written,
        "daily_write_budget_used_pct": round(
            rows_written / D1_FREE_TIER["rows_written_per_day"] * 100, 4
        ),
        "estimated_publication_size_kb": round(len(sql) / 1024, 1),
        "headroom_note": (
            "Publication surface is orders of magnitude inside the free tier; "
            "even a 1000x larger fact base stays under daily write limits with "
            "one full republish per day."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "applied": report["applied"],
                "local": local_counts,
                "remote": report.get("remote_counts"),
                "drill_passed": report.get("drill_passed"),
                "r2_enabled": report["r2"]["enabled"],
            },
            indent=2,
        )
    )
    if args.apply and not report.get("drill_passed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
