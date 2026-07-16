// JS port of apps/api/app/scoring.py relationship_score_metrics.
// The cloud Worker serves score explanations for PUBLISHED relationships
// only, so only that metric family is ported. Any change to the Python
// source must keep tests/scoring-parity green (make test-cloud-parity) -
// parity failure blocks release per S10PA stop condition.

export const CANDIDATE_SOURCE_THRESHOLD_MIN = 2;
export const SCORING_SERVICE_VERSION = "candidate-score-explanation-v1";

// CPython round(x, 2) rounds the exact decimal expansion of the binary
// double, ties-to-even. Number.prototype.toFixed(20) exposes a correctly
// rounded 20-digit decimal expansion, which is exact enough for score
// values (< 1000, >= 0); decimal-string rounding on top of it reproduces
// Python semantics bit-for-bit across the parity grid.
export function pythonRound2(value) {
  if (!Number.isFinite(value)) return value;
  const negative = value < 0;
  const text = Math.abs(value).toFixed(20);
  const dot = text.indexOf(".");
  const integerPart = text.slice(0, dot);
  const decimals = text.slice(dot + 1);
  const kept = decimals.slice(0, 2);
  const rest = decimals.slice(2);
  let units = BigInt(integerPart) * 100n + BigInt(kept);
  const restTrimmed = rest.replace(/0+$/, "");
  if (restTrimmed.length > 0) {
    const lead = rest.charCodeAt(0) - 48;
    if (lead > 5) {
      units += 1n;
    } else if (lead === 5) {
      if (restTrimmed.length > 1) {
        units += 1n;
      } else if (units % 2n === 1n) {
        units += 1n;
      }
    }
  }
  const result = Number(units) / 100;
  return negative ? -result : result;
}

export function relationshipScoreMetrics({
  confidence,
  independentSourceCount,
  sourceThresholdMet,
  reviewStatus,
  publicationStatus,
  factVersionPresent,
  evidencePresent,
  minimumIndependentSources = CANDIDATE_SOURCE_THRESHOLD_MIN
}) {
  const minimumSources = Math.max(minimumIndependentSources, 1);
  const sourceThresholdRatio = Math.min(independentSourceCount / minimumSources, 1);
  const rawScore = pythonRound2(confidence * 100);
  const evidenceQuality = pythonRound2(sourceThresholdRatio * 100);
  const adjustedScore = pythonRound2(rawScore * (evidenceQuality / 100));
  const presentInputs = [
    confidence !== null && confidence !== undefined,
    independentSourceCount !== null && independentSourceCount !== undefined,
    Boolean(reviewStatus),
    factVersionPresent,
    evidencePresent
  ];
  const coverage = pythonRound2(
    (presentInputs.filter(Boolean).length / presentInputs.length) * 100
  );
  const missingInputs = [];
  if (!sourceThresholdMet) {
    missingInputs.push(`independent_source_threshold>=${minimumSources}`);
  }
  if (reviewStatus !== "human_verified") {
    missingInputs.push("human_review_verification");
  }
  if (publicationStatus !== "published") {
    missingInputs.push("published_relationship_version");
  }
  if (!factVersionPresent) {
    missingInputs.push("relationship_fact_version");
  }
  if (!evidencePresent) {
    missingInputs.push("evidence_chain");
  }
  return {
    source_threshold: {
      minimum_independent_sources: minimumSources,
      independent_source_count: independentSourceCount,
      met: sourceThresholdMet
    },
    raw_score: rawScore,
    evidence_quality: evidenceQuality,
    adjusted_score: adjustedScore,
    coverage,
    contributions: [
      {
        input: "relationship_confidence",
        value: confidence,
        score_points: rawScore
      },
      {
        input: "independent_source_count",
        value: independentSourceCount,
        score_multiplier: sourceThresholdRatio
      },
      {
        input: "review_status",
        value: reviewStatus,
        publication_gate_passed: reviewStatus === "human_verified"
      },
      {
        input: "publication_status",
        value: publicationStatus,
        included_in_graph_edges: publicationStatus === "published"
      },
      {
        input: "fact_version",
        value: factVersionPresent,
        versioned_fact_available: factVersionPresent
      }
    ],
    missing_inputs: missingInputs
  };
}
