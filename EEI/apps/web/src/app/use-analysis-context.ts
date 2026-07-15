"use client";

import { useEffect, useState } from "react";
import {
  ACTIVE_ANALYSIS_CONTEXT,
  ANALYSIS_PREVIEW_STORAGE_KEY,
  PREVIEW_ANALYSIS_CONTEXT,
  type AnalysisContext,
  type ServerContextState
} from "./analysis-contract";
import { readProductionDataApiBaseUrl } from "./production-data-client";

type ServerActiveContextPayload = {
  schema_version?: string;
  active_data_snapshot_key?: string | null;
  active_scoring_run_id?: string | null;
  refresh_token?: string | null;
  refresh_generation?: number | null;
  model_version?: string | null;
  profile_version?: string | null;
  activated_at?: string | null;
};

export function useAnalysisContext() {
  const [analysisContext, setAnalysisContext] = useState<AnalysisContext>(ACTIVE_ANALYSIS_CONTEXT);
  const [serverState, setServerState] = useState<ServerContextState>({
    mode: "fixture_fallback",
    reason: "server_context_not_fetched"
  });

  useEffect(() => {
    const stored = window.localStorage.getItem(ANALYSIS_PREVIEW_STORAGE_KEY);
    if (stored === PREVIEW_ANALYSIS_CONTEXT.profileVersion) {
      setAnalysisContext(PREVIEW_ANALYSIS_CONTEXT);
      return;
    }
    void hydrateServerContext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function hydrateServerContext() {
    const apiBaseUrl = readProductionDataApiBaseUrl();
    if (!apiBaseUrl) {
      setServerState({ mode: "api_required", reason: "api_base_missing" });
      return;
    }
    try {
      const response = await window.fetch(`${apiBaseUrl}/v1/scoring/active-context`);
      const payload = (await response.json().catch(() => null)) as
        | ServerActiveContextPayload
        | null;
      if (!response.ok || !payload || payload.schema_version !== "active-analysis-context-v1") {
        setServerState({
          mode: "fixture_fallback",
          reason: `active_context_http_${response.status}`
        });
        return;
      }
      setAnalysisContext((current) => ({
        ...current,
        dataSnapshot: payload.active_data_snapshot_key ?? current.dataSnapshot,
        scoreSnapshot: payload.active_scoring_run_id ?? current.scoreSnapshot,
        modelVersion: payload.model_version ?? current.modelVersion,
        profileVersion: payload.profile_version ?? current.profileVersion
      }));
      setServerState({
        mode: "live",
        refreshToken: payload.refresh_token ?? null,
        refreshGeneration: payload.refresh_generation ?? null,
        activatedAt: payload.activated_at ?? null
      });
    } catch {
      setServerState({ mode: "fixture_fallback", reason: "active_context_fetch_failed" });
    }
  }

  function applyPreview() {
    window.localStorage.setItem(
      ANALYSIS_PREVIEW_STORAGE_KEY,
      PREVIEW_ANALYSIS_CONTEXT.profileVersion
    );
    setAnalysisContext(PREVIEW_ANALYSIS_CONTEXT);
  }

  function clearPreview() {
    window.localStorage.removeItem(ANALYSIS_PREVIEW_STORAGE_KEY);
    setAnalysisContext(ACTIVE_ANALYSIS_CONTEXT);
  }

  function applyServerContext(nextContext: AnalysisContext) {
    window.localStorage.removeItem(ANALYSIS_PREVIEW_STORAGE_KEY);
    setAnalysisContext(nextContext);
  }

  return {
    analysisContext,
    serverState,
    applyPreview,
    applyServerContext,
    clearPreview,
    isPreviewActive: analysisContext.profileVersion === PREVIEW_ANALYSIS_CONTEXT.profileVersion
  };
}
