"use client";

// EEI-F01/F02 (J-003/J-004): cloud-mode data loaders. The cloud publication
// surface exposes /v1/scoring/relationship/:id/explanation and
// /v1/evidence/relationship/:id (relationship ids come straight from the
// live graph edges), which differ from the local API's candidate-oriented
// endpoints. These loaders adapt the cloud responses onto the same record
// shapes the workspace already renders, so production hydrates real
// published data instead of falling back to fixtures.

import {
  readProductionDataApiBaseUrl,
  type EvidenceDetailItem,
  type EvidenceDetailRecord,
  type ScoreExplanationRecord,
  type SourceFreshnessRecord
} from "./production-data-client";

type CloudResult<T> =
  | { mode: "local_fallback"; status: "skipped"; reason: string }
  | { mode: "server"; status: "error"; endpoint: string; reason: string }
  | { mode: "server"; status: "hydrated"; endpoint: string; record: T };

type CloudEvidenceRow = {
  relationship_id: string;
  source_document_id: string;
  role: string;
  locator: string | null;
  support_excerpt: string | null;
  source_url: string | null;
  source_title: string | null;
  publisher: string | null;
  document_date: string | null;
};

export async function loadCloudScoreExplanation(
  relationshipId: string
): Promise<CloudResult<ScoreExplanationRecord>> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "local_fallback", status: "skipped", reason: "api_base_missing" };
  }
  const endpoint = `${apiBaseUrl}/v1/scoring/relationship/${relationshipId}/explanation`;
  try {
    const response = await window.fetch(endpoint, { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as
      | ScoreExplanationRecord
      | null;
    if (!response.ok || !payload || typeof payload.adjusted_score !== "number") {
      return {
        mode: "server",
        status: "error",
        endpoint,
        reason: `http_${response.status}`
      };
    }
    return { mode: "server", status: "hydrated", endpoint, record: payload };
  } catch {
    return { mode: "server", status: "error", endpoint, reason: "fetch_failed" };
  }
}

export async function loadCloudEvidenceDetail(
  relationshipId: string
): Promise<CloudResult<EvidenceDetailRecord>> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "local_fallback", status: "skipped", reason: "api_base_missing" };
  }
  const endpoint = `${apiBaseUrl}/v1/evidence/relationship/${relationshipId}`;
  try {
    const response = await window.fetch(endpoint, { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as {
      object_id?: string;
      evidence?: CloudEvidenceRow[];
      evidence_count?: number;
    } | null;
    if (!response.ok || !payload || !Array.isArray(payload.evidence)) {
      return {
        mode: "server",
        status: "error",
        endpoint,
        reason: `http_${response.status}`
      };
    }
    const items: EvidenceDetailItem[] = payload.evidence.map((row) => ({
      evidence_id: `${row.relationship_id}:${row.source_document_id}:${row.role}`,
      source_document_id: row.source_document_id,
      ingestion_evidence_chain_id: null,
      role: row.role,
      source_tier: 1,
      publisher: row.publisher,
      title: row.source_title,
      url: row.source_url,
      locator: row.locator,
      support_excerpt: row.support_excerpt,
      snippet: {
        text: row.support_excerpt,
        locator: row.locator,
        redaction_status: "public"
      },
      structured_fact: {},
      counter_evidence: [],
      parser_version: null,
      confidence: null,
      review_status: "human_verified",
      source_document: {
        url: row.source_url,
        title: row.source_title,
        publisher: row.publisher,
        document_date: row.document_date
      }
    }));
    const documentIds = new Set(items.map((item) => item.source_document_id));
    const record: EvidenceDetailRecord = {
      schema_version: "evidence-detail-v1",
      object_type: "relationship",
      object_id: payload.object_id ?? relationshipId,
      object_summary: {},
      evidence_count: payload.evidence_count ?? items.length,
      returned_evidence_count: items.length,
      source_document_count: documentIds.size,
      limit: items.length,
      truncated: false,
      source_documents: items.map((item) => item.source_document),
      evidence: items,
      production_context: {}
    };
    return { mode: "server", status: "hydrated", endpoint, record };
  } catch {
    return { mode: "server", status: "error", endpoint, reason: "fetch_failed" };
  }
}

// The publication surface's freshness truth is the publication itself: when
// the surface was last republished and which snapshot identity it carries.
export async function loadCloudPublicationFreshness(): Promise<
  CloudResult<SourceFreshnessRecord>
> {
  const apiBaseUrl = readProductionDataApiBaseUrl();
  if (!apiBaseUrl) {
    return { mode: "local_fallback", status: "skipped", reason: "api_base_missing" };
  }
  const endpoint = `${apiBaseUrl}/v1/publication/meta`;
  try {
    const response = await window.fetch(endpoint, { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as {
      publication_meta?: Record<string, string>;
      snapshot?: { snapshot_key?: string; as_of?: string | null } | null;
    } | null;
    if (!response.ok || !payload?.publication_meta) {
      return {
        mode: "server",
        status: "error",
        endpoint,
        reason: `http_${response.status}`
      };
    }
    const publishedAt = payload.publication_meta.published_at ?? null;
    const record: SourceFreshnessRecord = {
      schema_version: "source-freshness-v1",
      as_of: publishedAt ?? "",
      summary: {
        status: "available",
        source_count: 1,
        available_source_count: 1,
        failed_source_count: 0,
        running_source_count: 0,
        attempt_count: 1,
        success_count: 1,
        failure_count: 0,
        document_count: 0,
        last_attempt_at: publishedAt,
        last_success_at: publishedAt,
        last_failure_at: null,
        latest_document_date: payload.snapshot?.as_of ?? null,
        latest_report_period_end: payload.snapshot?.as_of ?? null
      },
      sources: [
        {
          source_id: "cloud-publication",
          source_code: "cloud_publication_surface",
          source_name: "EEI 发布面（一次一致性发布）",
          source_tier: 1,
          expected_cadence: null,
          typical_disclosure_lag: null,
          last_verified_at: publishedAt,
          record_modes: ["database"],
          data_mode: "live",
          freshness_status: "available",
          attempt_count: 1,
          success_count: 1,
          failure_count: 0,
          last_attempt_at: publishedAt,
          last_attempt_finished_at: publishedAt,
          last_attempt_status: "succeeded",
          last_success_at: publishedAt,
          last_failure_at: null,
          last_error_class: null,
          last_error_message: null,
          document_count: 0,
          latest_document_date: payload.snapshot?.as_of ?? null,
          latest_report_period_start: null,
          latest_report_period_end: payload.snapshot?.as_of ?? null,
          latest_observed_at: publishedAt,
          latest_retrieved_at: publishedAt
        }
      ],
      semantics: {
        attempt_time_is_document_time: false
      }
    } as SourceFreshnessRecord;
    return { mode: "server", status: "hydrated", endpoint, record };
  } catch {
    return { mode: "server", status: "error", endpoint, reason: "fetch_failed" };
  }
}
