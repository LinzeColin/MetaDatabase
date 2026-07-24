import { expect, test, type BrowserContext, type Page, type Request } from "@playwright/test";

const apiBaseUrl = "http://capital.eei.test";
const apiBaseStorageKey = "eei.productionDataApiBaseUrl.v1";
const capexEventId = "30000000-0000-4000-8000-000000000002";
const awardEventId = "30000000-0000-4000-8000-000000000003";
const unknownEventId = "30000000-0000-4000-8000-000000000001";

const events = [
  {
    id: capexEventId,
    event_type: "capital_expenditure",
    title: "AI infrastructure capex",
    status: "reported",
    announced_at: "2026-01-15T00:00:00Z",
    effective_at: null,
    period_start: "2026-01-01",
    period_end: "2026-12-31",
    observed_at: "2026-06-19T00:00:00Z",
    amount: 1_000_000_000,
    currency: "USD",
    amount_kind: "period_capex",
    description: "Reported period capex",
    qualifiers: {},
    evidence_count: 1,
    participants: [
      {
        entity_id: "00000000-0000-4000-8000-000000000001",
        role: "spender",
        direction: "out"
      }
    ],
    amount_semantics: {
      schema_version: "event-amount-semantics-v1",
      state: "reported",
      amount: 1_000_000_000,
      display_amount: 1_000_000_000,
      currency: "USD",
      amount_kind: "period_capex",
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      visual_weight: 1_000_000_000,
      width_eligible: true,
      aggregate_eligible: true,
      aggregation_key: {
        currency: "USD",
        amount_kind: "period_capex",
        period_start: "2026-01-01",
        period_end: "2026-12-31"
      },
      non_aggregation_reason: null
    }
  },
  {
    id: awardEventId,
    event_type: "contract_award",
    title: "Government award ceiling",
    status: "reported",
    announced_at: "2025-10-01T00:00:00Z",
    effective_at: "2025-10-01T00:00:00Z",
    period_start: null,
    period_end: null,
    observed_at: "2026-06-19T00:00:00Z",
    amount: 500_000_000,
    currency: "USD",
    amount_kind: "award_ceiling",
    description: "Ceiling, not paid cash",
    qualifiers: {},
    evidence_count: 1,
    participants: [
      {
        entity_id: "00000000-0000-4000-8000-000000000019",
        role: "awarder",
        direction: "out"
      },
      {
        entity_id: "00000000-0000-4000-8000-000000000009",
        role: "awardee",
        direction: "in"
      }
    ],
    amount_semantics: {
      schema_version: "event-amount-semantics-v1",
      state: "reported",
      amount: 500_000_000,
      display_amount: 500_000_000,
      currency: "USD",
      amount_kind: "award_ceiling",
      period_start: null,
      period_end: null,
      visual_weight: 500_000_000,
      width_eligible: true,
      aggregate_eligible: true,
      aggregation_key: {
        currency: "USD",
        amount_kind: "award_ceiling",
        period_start: null,
        period_end: null
      },
      non_aggregation_reason: null
    }
  },
  {
    id: unknownEventId,
    event_type: "funding_round",
    title: "Disclosed funding event without amount",
    status: "reported",
    announced_at: "2026-02-27T00:00:00Z",
    effective_at: null,
    period_start: null,
    period_end: null,
    observed_at: "2026-06-19T00:00:00Z",
    amount: null,
    currency: null,
    amount_kind: null,
    description: "Amount not disclosed",
    qualifiers: {},
    evidence_count: 1,
    participants: [
      {
        entity_id: "00000000-0000-4000-8000-000000000012",
        role: "recipient",
        direction: "in"
      }
    ],
    amount_semantics: {
      schema_version: "event-amount-semantics-v1",
      state: "unreported",
      amount: null,
      display_amount: null,
      currency: null,
      amount_kind: null,
      period_start: null,
      period_end: null,
      visual_weight: null,
      width_eligible: false,
      aggregate_eligible: false,
      aggregation_key: null,
      non_aggregation_reason: "amount_unreported"
    }
  }
];

const amountSummary = {
  schema_version: "event-amount-semantics-v1",
  event_count: 3,
  reported_event_count: 2,
  unreported_event_count: 1,
  unclassified_event_count: 0,
  bucket_count: 2,
  buckets: [
    {
      currency: "USD",
      amount_kind: "award_ceiling",
      period_start: null,
      period_end: null,
      total_amount: 500_000_000,
      visual_weight_total: 500_000_000,
      event_count: 1,
      event_ids: [awardEventId]
    },
    {
      currency: "USD",
      amount_kind: "period_capex",
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      total_amount: 1_000_000_000,
      visual_weight_total: 1_000_000_000,
      event_count: 1,
      event_ids: [capexEventId]
    }
  ],
  unreported_event_ids: [unknownEventId],
  unclassified_event_ids: [],
  incomparable_dimensions: ["amount_kind", "period"],
  cross_bucket_summation_performed: false,
  comparable_reported_total_available: false,
  comparable_reported_total: null,
  comparable_reported_total_complete: false,
  semantics: {
    unknown_amount_is_zero: false,
    unknown_amount_has_visual_weight: false,
    aggregation_key: ["currency", "amount_kind", "period_start", "period_end"],
    incomparable_buckets_are_summed: false
  },
  filters: { limit: 100 }
};

async function configureApi(context: BrowserContext) {
  await context.addInitScript(
    ({ key, value }: { key: string; value: string }) => window.localStorage.setItem(key, value),
    { key: apiBaseStorageKey, value: apiBaseUrl }
  );
}

async function mockCapitalApi(page: Page, requestUrls: string[]) {
  await page.route(`${apiBaseUrl}/v1/**`, async (route) => {
    const url = new URL(route.request().url());
    requestUrls.push(url.toString());
    if (url.pathname === "/v1/events") {
      await route.fulfill({ json: events });
      return;
    }
    if (url.pathname === "/v1/events/amount-summary") {
      await route.fulfill({ json: amountSummary });
      return;
    }
    if (url.pathname === `/v1/evidence/event/${capexEventId}`) {
      await route.fulfill({
        json: {
          schema_version: "evidence-detail-v1",
          object_type: "event",
          object_id: capexEventId,
          object_summary: events[0],
          evidence_count: 1,
          returned_evidence_count: 1,
          source_document_count: 1,
          limit: 20,
          truncated: false,
          source_documents: [],
          evidence: [
            {
              evidence_id: `${capexEventId}:source:supports`,
              source_document_id: "20000000-0000-4000-8000-000000000031",
              ingestion_evidence_chain_id: null,
              role: "supports",
              source_tier: 1,
              publisher: "SEC EDGAR",
              title: "Capital expenditure disclosure",
              url: "https://www.sec.gov/example-capex",
              locator: "Item 7",
              support_excerpt: "Capital expenditures are expected during the reported period.",
              snippet: {
                text: "Capital expenditures are expected during the reported period.",
                locator: "Item 7",
                redaction_status: "none"
              },
              structured_fact: {},
              counter_evidence: [],
              parser_version: "fixture-v1",
              confidence: null,
              review_status: "event_evidence",
              source_document: {}
            }
          ],
          production_context: { schema_version: "production-context-v1" }
        }
      });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "not found" } });
  });
}

test.beforeEach(async ({ context, page }) => {
  await configureApi(context);
  await mockCapitalApi(page, []);
});

test("A108 and A109 keep unknown and incomparable event amounts visually separate", async ({
  page
}) => {
  await page.goto("/capital");

  const shell = page.getByTestId("capital-river-shell");
  await expect(shell).toHaveAttribute("data-load-state", "hydrated");
  await expect(shell).toHaveAttribute("data-cross-bucket-summation", "false");
  const summary = page.getByTestId("capital-amount-summary");
  await expect(summary).toHaveAttribute("data-bucket-count", "2");
  await expect(summary).toHaveAttribute("data-comparable-total-available", "false");
  await expect(page.getByTestId("capital-cross-bucket-total")).toHaveText("禁用");

  await expect(page.getByTestId(`capital-event-${capexEventId}`)).toHaveAttribute(
    "data-has-flow-width",
    "true"
  );
  await expect(page.getByTestId(`capital-event-${awardEventId}`)).toHaveAttribute(
    "data-has-flow-width",
    "true"
  );
  const unknownEvent = page.getByTestId(`capital-event-${unknownEventId}`);
  await expect(unknownEvent).toHaveAttribute("data-has-flow-width", "false");
  await expect(unknownEvent).toContainText("未披露");
  await expect(unknownEvent.locator(".capitalFlowTrack")).toHaveCount(0);

  await expect(page.locator("[data-aggregation-key*='period_capex']")).toHaveCount(1);
  await expect(page.locator("[data-aggregation-key*='award_ceiling']")).toHaveCount(1);
});

test("A110 applies Capital River filters and opens event evidence", async ({ page }) => {
  const requestUrls: string[] = [];
  await page.unroute(`${apiBaseUrl}/v1/**`);
  await mockCapitalApi(page, requestUrls);
  await page.goto("/capital");

  await page.getByTestId("capital-filter-entity").fill(
    "00000000-0000-4000-8000-000000000001"
  );
  await page.getByTestId("capital-filter-from").fill("2026-01-01");
  await page.getByTestId("capital-filter-to").fill("2026-12-31");
  await page.getByTestId("capital-filter-event-type").fill("capital_expenditure");
  await page.getByTestId("capital-filter-currency").fill("usd");
  await page.getByTestId("capital-filter-amount-kind").fill("period_capex");
  // Apply must send /v1/events and /v1/events/amount-summary carrying the full
  // filter set. Wait for the FULLY-APPLIED request (matched on entity +
  // amount_kind) tied to the click, not merely one with amount_kind: under CI
  // load the capital page can emit a transient period_capex fetch before the
  // entity filter is committed, and matching only on amount_kind captured that
  // partial request → intermittent entity-assertion flake. Matching on the
  // applied entity ignores the transient one; if the fully-applied request
  // never fires, waitForRequest times out (a real dropped-filter bug still
  // fails). All six params are then verified on the captured requests.
  const APPLIED: Record<string, string> = {
    entity: "00000000-0000-4000-8000-000000000001",
    from: "2026-01-01T00:00:00.000Z",
    to: "2026-12-31T23:59:59.999Z",
    event_type: "capital_expenditure",
    currency: "USD",
    amount_kind: "period_capex"
  };
  const appliedRequest = (pathname: string) => (request: Request) => {
    const url = new URL(request.url());
    return (
      url.pathname === pathname &&
      url.searchParams.get("amount_kind") === APPLIED.amount_kind &&
      url.searchParams.get("entity") === APPLIED.entity
    );
  };
  const [eventsRequest, summaryRequest] = await Promise.all([
    page.waitForRequest(appliedRequest("/v1/events")),
    page.waitForRequest(appliedRequest("/v1/events/amount-summary")),
    page.getByTestId("capital-filter-apply").click()
  ]);
  await expect(page.getByTestId("capital-river-shell")).toHaveAttribute(
    "data-load-state",
    "hydrated"
  );

  for (const request of [eventsRequest, summaryRequest]) {
    const url = new URL(request.url());
    for (const [key, value] of Object.entries(APPLIED)) {
      expect(url.searchParams.get(key)).toBe(value);
    }
  }

  await page.getByTestId(`capital-open-evidence-${capexEventId}`).click();
  await expect(page.getByTestId("capital-event-evidence")).toHaveAttribute(
    "data-evidence-state",
    "hydrated"
  );
  await expect(page.getByTestId("capital-event-evidence")).toHaveAttribute(
    "data-selected-event-id",
    capexEventId
  );
  await expect(page.getByTestId("capital-evidence-count")).toHaveText("1");
  await expect(page.getByTestId("capital-evidence-list")).toContainText("SEC EDGAR");
  await expect(page.getByTestId("capital-evidence-list")).toContainText(
    "Capital expenditures are expected"
  );
  expect(requestUrls).toContain(`${apiBaseUrl}/v1/evidence/event/${capexEventId}?limit=20`);

  // P0-1：证据中心不再是导航项——它是首页常驻右栏（§A.3），直达可见。
  await page.goto("/");
  await expect(page.getByTestId("evidence-center")).toBeVisible();
});
