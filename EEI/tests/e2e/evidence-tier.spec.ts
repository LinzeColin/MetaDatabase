import { expect, test } from "@playwright/test";

// 官方单来源可上图（Owner 2026-09-30）：发布闸门给每条边盖的章
// （单一官方来源 / 多来源交叉核实）必须在证据面板上说出来，
// 且官方原文链接可点开。

const REL_ID = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff";

async function mockSupplyChain(page: import("@playwright/test").Page, tier: string | null) {
  await page.addInitScript(() => {
    window.localStorage.setItem("eei.apiBaseUrl.v1", "http://127.0.0.1:3000");
  });
  await page.route("**/v1/supply-chain/overview", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        stages: [
          {
            stage_id: "S01",
            stage_order: 1,
            slug: "foundry",
            name_zh: "制造",
            name_en: "Manufacturing",
            default_direction: "up",
            examples: null
          }
        ],
        relationships: [
          {
            id: REL_ID,
            relationship_type: "wafer_foundry_for",
            status: "published",
            confidence: 0.95,
            observed_at: null,
            owner_signed_published: false,
            subject_name: "ACME Trading Ltd",
            object_name: "ACME Holdings plc",
            fixture_flag: false,
            stage_id: "S01"
          }
        ],
        summary: {
          published_fact_count: 1,
          demo_or_candidate_count: 0,
          stages_total: 1,
          stages_with_relationships: 1
        },
        abstentions: {}
      })
    })
  );
  await page.route(`**/v1/evidence/relationship/${REL_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        object_type: "relationship",
        object_id: REL_ID,
        evidence_tier: tier,
        evidence: [
          {
            relationship_id: REL_ID,
            source_document_id: "doc-gleif",
            role: "supports",
            locator: "GLEIF direct-children relationship",
            support_excerpt: "ACME Trading Ltd is a direct subsidiary of ACME Holdings plc per GLEIF.",
            source_url: "https://api.gleif.org/api/v1/lei-records/549300ACME/direct-children",
            source_title: "GLEIF relationship for ACME Holdings plc",
            publisher: "Global LEI Foundation",
            document_date: "2026-07-14"
          }
        ],
        evidence_count: 1
      })
    })
  );
}

test("single official source edge says so and links the original", async ({ page }) => {
  await mockSupplyChain(page, "single_official");
  await page.goto("/supply-chain");
  await page.getByTestId(`supply-evidence-open-${REL_ID}`).click();
  const chip = page.getByTestId("supply-chain-evidence-tier");
  await expect(chip).toBeVisible({ timeout: 2000 });
  await expect(chip).toHaveText("单一官方来源");
  await expect(chip).toHaveAttribute("data-evidence-tier", "single_official");
  const link = page.getByTestId("supply-chain-evidence-source-0");
  await expect(link).toHaveAttribute(
    "href",
    "https://api.gleif.org/api/v1/lei-records/549300ACME/direct-children"
  );
  await expect(link).toHaveAttribute("target", "_blank");
});

test("multi-source edge is labelled as cross-verified, not as single official", async ({
  page
}) => {
  await mockSupplyChain(page, "multi_source");
  await page.goto("/supply-chain");
  await page.getByTestId(`supply-evidence-open-${REL_ID}`).click();
  const chip = page.getByTestId("supply-chain-evidence-tier");
  await expect(chip).toHaveText("多来源交叉核实");
});

test("an edge with no recorded tier gets no tier stamp", async ({ page }) => {
  await mockSupplyChain(page, null);
  await page.goto("/supply-chain");
  await page.getByTestId(`supply-evidence-open-${REL_ID}`).click();
  await expect(page.getByTestId("supply-chain-evidence-conclusion")).toBeVisible({
    timeout: 2000
  });
  await expect(page.getByTestId("supply-chain-evidence-tier")).toHaveCount(0);
});
