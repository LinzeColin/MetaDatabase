import { expect, test } from "@playwright/test";

// P1-6 五态组件库 / P1-7 动效 token / P1-8 证据下钻 的 e2e 契约。

const REL_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

// —— P1-6：骨架屏延迟出现，刷新不清屏 ————————————————————————————————
test("stalled first load shows the shared skeleton (delayed, not a spinner)", async ({
  page
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("eei.apiBaseUrl.v1", "http://127.0.0.1:3000");
  });
  // 首个 overview 永不返回 → loadState 卡在 loading、无数据 → 同构骨架出现。
  await page.route("**/v1/supply-chain/overview", () => {
    /* never fulfilled */
  });
  await page.goto("/supply-chain");
  const skeleton = page.getByTestId("supply-chain-skeleton");
  await expect(skeleton).toBeVisible({ timeout: 2000 });
  // 延迟闸门在 100ms 后置 data-shown=true（<100ms 快返回则从不显形）。
  await expect(skeleton).toHaveAttribute("data-shown", "true");
});

// —— P1-7：reduced-motion 令新交互 token 归零（总闸全灭）——————————————
test("reduced-motion collapses token-driven interaction transitions", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/");
  const navDuration = await page.evaluate(() => {
    const el = document.querySelector(".navItem");
    return el ? getComputedStyle(el).transitionDuration : "missing";
  });
  // --motion-fast 挂 --motion-scale；scale=0 + L66 兜底 → 1ms。
  expect(navDuration).toBe("0.001s");
  await context.close();
});

test("normal motion keeps interaction transitions non-zero", async ({ page }) => {
  await page.goto("/");
  const navDuration = await page.evaluate(() => {
    const el = document.querySelector(".navItem");
    return el ? getComputedStyle(el).transitionDuration : "missing";
  });
  // --motion-fast = calc(1 * 100ms + 0.001s) ≈ 0.101s（> 0 即证明走的是 token）。
  expect(navDuration).not.toBe("0.001s");
  expect(navDuration).not.toBe("0s");
});

// —— P1-8：供应链关系行两步下钻见摘录 + 官方链接 ————————————————————————
test("supply-chain relationship row drills down to excerpt and official source", async ({
  page
}) => {
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
            confidence: 0.92,
            observed_at: null,
            owner_signed_published: true,
            subject_name: "NVIDIA Corporation",
            object_name: "TSMC",
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
        evidence: [
          {
            relationship_id: REL_ID,
            source_document_id: "doc-1",
            role: "supporting",
            locator: "10-K 2024 · Exhibit 21",
            support_excerpt: "TSMC manufactures NVIDIA's advanced GPUs on leading-edge nodes.",
            source_url: "https://www.sec.gov/example-10k",
            source_title: "NVIDIA 10-K (2024)",
            publisher: "SEC EDGAR",
            document_date: "2024-02-21"
          }
        ],
        evidence_count: 1
      })
    })
  );

  await page.goto("/supply-chain");
  // 第一步：点关系行的「查证」。
  await page.getByTestId(`supply-evidence-open-${REL_ID}`).click();
  // 第二步：右栏证据三段式。① 结论人话句
  const conclusion = page.getByTestId("supply-chain-evidence-conclusion");
  await expect(conclusion).toBeVisible({ timeout: 2000 });
  await expect(conclusion).toContainText("NVIDIA Corporation");
  await expect(conclusion).toContainText("TSMC");
  // ② 摘录 + 定位
  await expect(page.getByTestId("supply-chain-evidence-locator-0")).toContainText("Exhibit 21");
  await expect(page.getByTestId("supply-chain-evidence-list")).toContainText("TSMC manufactures");
  // ③ 官方源真链接
  const link = page.getByTestId("supply-chain-evidence-source-0");
  await expect(link).toHaveAttribute("href", "https://www.sec.gov/example-10k");
  await expect(link).toHaveAttribute("target", "_blank");
});
