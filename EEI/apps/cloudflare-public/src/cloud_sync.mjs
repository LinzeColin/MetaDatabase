// EEI cloud incremental collection (S10PBT02). A daily Worker cron polls
// SEC EDGAR submissions for the tracked research companies in rotating
// slices (ADP-style rotation keeps each run inside free-tier quota and
// SEC fair-use limits) and records an honest run_log row either way.
// Publishing stays owner-gated on the local factory; this surface only
// tracks fresh-filing signals and proves 7x24 cloud operation.

export const TRACKED_COMPANIES = [
  { research_id: "P0-001", cik: 1652044, name: "Alphabet Inc." },
  { research_id: "P0-002", cik: 789019, name: "Microsoft Corporation" },
  { research_id: "P0-003", cik: 1018724, name: "Amazon.com, Inc." },
  { research_id: "P0-004", cik: 1326801, name: "Meta Platforms, Inc." },
  { research_id: "P0-005", cik: 320193, name: "Apple Inc." },
  { research_id: "P0-006", cik: 1045810, name: "NVIDIA Corporation" },
  { research_id: "P0-012", cik: 1318605, name: "Tesla, Inc." },
  { research_id: "P0-013", cik: 1341439, name: "Oracle Corporation" },
  { research_id: "P0-014", cik: 1730168, name: "Broadcom Inc." },
  { research_id: "P0-017", cik: 1769628, name: "CoreWeave, Inc." },
  { research_id: "P0-018", cik: 1321655, name: "Palantir Technologies Inc." },
  { research_id: "X-001", cik: 1046179, name: "TSMC" },
  { research_id: "X-002", cik: 937966, name: "ASML Holding N.V." }
];

export const ROTATION_SLICE_SIZE = 5;
const RECENT_WINDOW_DAYS = 4;

function paddedCik(cik) {
  return String(cik).padStart(10, "0");
}

export function rotationSlice(runIndex, companies = TRACKED_COMPANIES, sliceSize = ROTATION_SLICE_SIZE) {
  const sliceCount = Math.ceil(companies.length / sliceSize);
  const slice = ((runIndex % sliceCount) + sliceCount) % sliceCount;
  return {
    slice,
    slice_count: sliceCount,
    companies: companies.slice(slice * sliceSize, slice * sliceSize + sliceSize)
  };
}

async function fetchRecentFilings(company, userAgent, sinceIso) {
  const url = `https://data.sec.gov/submissions/CIK${paddedCik(company.cik)}.json`;
  const response = await fetch(url, {
    headers: { "user-agent": userAgent, accept: "application/json" }
  });
  if (!response.ok) {
    return { company, status: `http_${response.status}`, recent_filings: [] };
  }
  const payload = await response.json();
  const recent = payload?.filings?.recent;
  const filings = [];
  if (recent?.accessionNumber) {
    for (let index = 0; index < recent.accessionNumber.length; index += 1) {
      const filingDate = recent.filingDate?.[index];
      if (!filingDate || filingDate < sinceIso) continue;
      filings.push({
        accession_number: recent.accessionNumber[index],
        form: recent.form?.[index] ?? null,
        filing_date: filingDate,
        primary_document: recent.primaryDocument?.[index] ?? null
      });
    }
  }
  return { company, status: "ok", recent_filings: filings };
}

export async function runCloudSync(env, trigger) {
  const startedAt = new Date().toISOString();
  const runId = crypto.randomUUID();
  const userAgent = env.SEC_USER_AGENT || "EEI research linzezhang35@gmail.com";
  const countRow = await env.EEI_PUB.prepare(
    "SELECT COUNT(*) AS n FROM cloud_run_log"
  ).first();
  const runIndex = Number(countRow?.n ?? 0);
  const rotation = rotationSlice(runIndex);
  const sinceDate = new Date(Date.now() - RECENT_WINDOW_DAYS * 24 * 3600 * 1000);
  const sinceIso = sinceDate.toISOString().slice(0, 10);

  const results = [];
  let status = "completed";
  try {
    for (const company of rotation.companies) {
      results.push(await fetchRecentFilings(company, userAgent, sinceIso));
    }
    if (results.every((entry) => entry.status !== "ok")) {
      status = "failed";
    } else if (results.some((entry) => entry.status !== "ok")) {
      status = "partial";
    }
  } catch (error) {
    status = "failed";
    results.push({ error: String(error).slice(0, 300) });
  }
  const newCount = results.reduce(
    (total, entry) => total + (entry.recent_filings?.length ?? 0),
    0
  );
  const finishedAt = new Date().toISOString();
  await env.EEI_PUB.prepare(
    "INSERT INTO cloud_run_log(id, trigger, started_at, finished_at, status," +
      " rotation_slice, scope_json, new_filings_count, detail_json)" +
      " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
  )
    .bind(
      runId,
      trigger,
      startedAt,
      finishedAt,
      status,
      rotation.slice,
      JSON.stringify({
        since: sinceIso,
        slice: rotation.slice,
        slice_count: rotation.slice_count,
        companies: rotation.companies.map((company) => company.research_id)
      }),
      newCount,
      JSON.stringify(
        results.map((entry) => ({
          research_id: entry.company?.research_id ?? null,
          status: entry.status ?? "error",
          new_filings: (entry.recent_filings ?? []).slice(0, 20),
          error: entry.error ?? undefined
        }))
      )
    )
    .run();
  return { run_id: runId, status, rotation_slice: rotation.slice, new_filings_count: newCount };
}

export async function listCloudRuns(env, limit, json) {
  const bounded = Math.max(1, Math.min(Number.parseInt(limit ?? "10", 10) || 10, 50));
  const { results } = await env.EEI_PUB.prepare(
    "SELECT id, trigger, started_at, finished_at, status, rotation_slice," +
      " scope_json, new_filings_count, detail_json" +
      " FROM cloud_run_log ORDER BY started_at DESC LIMIT ?"
  )
    .bind(bounded)
    .all();
  return json(
    (results ?? []).map((row) => ({
      id: row.id,
      trigger: row.trigger,
      started_at: row.started_at,
      finished_at: row.finished_at,
      status: row.status,
      rotation_slice: row.rotation_slice,
      scope: JSON.parse(row.scope_json ?? "{}"),
      new_filings_count: row.new_filings_count,
      detail: JSON.parse(row.detail_json ?? "[]")
    }))
  );
}
