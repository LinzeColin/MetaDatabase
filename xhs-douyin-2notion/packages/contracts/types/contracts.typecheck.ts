import { canonicalPayloadJson } from "./contracts.ts";
import type {
  CompatibilityPolicy,
  NativeMessageRequest,
  Platform,
  ProvenanceChain,
} from "./contracts.ts";

const request: NativeMessageRequest = {
  schema_version: "1.0",
  request_id: "00000000-0000-4000-8000-000000000001",
  action: "capture_current",
  sent_at: "2026-07-20T00:00:00Z",
  payload: {
    platform: "xiaohongshu",
    page_url: "https://www.xiaohongshu.com/explore/synthetic-note-001",
    page_context: {
      content_id: "synthetic-note-001",
      title: null,
      content_type: "video",
    },
    relation: "saved_current",
    category_id: null,
    user_gesture: true,
    auto_scroll: false,
    change_account_state: false,
  },
  payload_hash: "0000000000000000000000000000000000000000000000000000000000000000",
};

const compatibility: CompatibilityPolicy = {
  schema_version: "1.0",
  contract_version: "1.0",
  accepted_read_versions: ["1.0"],
  compatibility_mode: "exact_match_fail_closed",
  unknown_fields: "reject",
  unknown_versions: "reject",
  destructive_migration: "forbidden_without_versioned_migration",
};

declare const trace: ProvenanceChain;
void request;
void compatibility;
void trace;
const canonicalPayload = canonicalPayloadJson(request.payload);
void canonicalPayload;

// @ts-expect-error unknown platforms must not silently widen the contract.
const invalidPlatform: Platform = "generic";
void invalidPlatform;
