"use strict";

// AC-040 AI 双流水线：软件测试与模型能力/安全结果分开，三类硬失败不被平均分覆盖
//
// 在此之前这一层根本不存在：软件测试跑 npm test，模型安全跑
// canonical-model-safety-evaluation，两边各出各的结果，**没有任何地方把它们放
// 在一起并守住那条规矩**。而 AC-040 要的恰恰是那个合并点上的性质。
//
// 这个文件里最重要的一条是「一次越权不许被 99 项通过稀释」——那正是
// 「不被平均分覆盖」这六个字的全部意思。

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  HARD_FAILURE_KINDS,
  buildDualPipelineReport,
} = require("../src/services/evaluation/dual-pipeline-report");

const clean = (n) => ({ total: n, passed: n, failed: 0, hard_failures: [] });

test("AC-040 两条流水线都干净时才通过", () => {
  const r = buildDualPipelineReport({ software: clean(1559), model: clean(6) });
  assert.equal(r.verdict, "PASS");
  assert.equal(r.hard_failures.length, 0);
});

test("AC-040 一次越权不许被 99 项通过稀释", () => {
  // 这是整条验收的重点。一个「99% 通过」的数字读起来很像进展，
  // 而它正好能把一次越权藏进那 1% 里——藏得体面、藏得可汇报。
  const r = buildDualPipelineReport({
    software: { total: 100, passed: 99, failed: 1,
      hard_failures: [{ kind: "privilege_escalation", detail: "访客读到了主人的数据" }] },
    model: clean(6),
  });
  assert.equal(r.verdict, "FAIL", "一次越权被通过率盖住了");
  assert.deepEqual(r.vetoed_by, ["software:privilege_escalation"]);
});

test("AC-040 三类硬失败各自都能一票否决", () => {
  for (const kind of HARD_FAILURE_KINDS) {
    const r = buildDualPipelineReport({
      software: { ...clean(1000), hard_failures: [{ kind, detail: "" }] },
      model: clean(6),
    });
    assert.equal(r.verdict, "FAIL", `${kind} 没有否决掉整份报告`);
  }
});

test("AC-040 否决权不看它来自哪条流水线", () => {
  // 软件那边发现的越权和模型那边发现的越权是同一件事。分开对待就给了
  // 「这条是 AI 侧的，算能力问题」一个口子。
  const fromModel = buildDualPipelineReport({
    software: clean(1559),
    model: { ...clean(6), hard_failures: [{ kind: "privacy_leak", detail: "" }] },
  });
  assert.equal(fromModel.verdict, "FAIL");
  assert.deepEqual(fromModel.vetoed_by, ["model:privacy_leak"]);
});

test("AC-040 报告里不许出现任何可以被当成分数的字段", () => {
  // 没有分数就没有分数可以稀释。这一条守的是「不被平均分覆盖」的根，
  // 比逐个断言判定结果更结实——够不着比「我们没算」强。
  const r = buildDualPipelineReport({ software: clean(1559), model: clean(6) });
  // 查**键名**，不查整份 JSON 文本：整份文本里 generated_at 含着 "rate"，
  // 按子串扫会误报，而误报会让人把这条守卫关掉——那才是真正的损失。
  const keys = [];
  const walk = (node) => {
    if (Array.isArray(node)) {
      node.forEach(walk);
    } else if (node && typeof node === "object") {
      for (const [k, v] of Object.entries(node)) {
        keys.push(k);
        walk(v);
      }
    }
  };
  walk(r);
  for (const banned of ["rate", "score", "percent", "average", "ratio", "grade"]) {
    const hit = keys.filter((k) => k !== "generated_at" && k.toLowerCase().includes(banned));
    assert.deepEqual(hit, [],
      `报告里出现了带 ${banned} 的字段 ${JSON.stringify(hit)}——一旦有分数，硬失败就有地方被稀释`);
  }
});

test("AC-040 两条流水线的数字不许被加到一起", () => {
  // 相加就等于给了它们一个共同分母，而共同分母就是平均分。
  const r = buildDualPipelineReport({ software: clean(1559), model: clean(6) });
  assert.equal(r.pipelines.software.total, 1559);
  assert.equal(r.pipelines.model.total, 6);
  const blob = JSON.stringify(r);
  assert.ok(!blob.includes("1565"), "两条流水线的总数被加到了一起（1559+6）");
});

test("AC-040 缺一条流水线是「不知道」，不是「通过」", () => {
  // 软件测试回答「代码按写的那样跑吗」，模型评估回答「它在被诱导时会做什么」。
  // 任何一条缺席，合并结果就是不知道——和 AC-025 分开 UNKNOWN 与 HEALTHY 同理。
  assert.equal(buildDualPipelineReport({ software: clean(1559), model: null }).verdict, "INCOMPLETE");
  assert.equal(buildDualPipelineReport({ software: null, model: clean(6) }).verdict, "INCOMPLETE");
  assert.equal(buildDualPipelineReport({}).verdict, "INCOMPLETE");
});

test("AC-040 已经发现的硬失败不许被「还没测完」盖过去", () => {
  // 判定顺序：先看硬失败，再看缺席。反过来写的话，一次已经测出来的越权会被
  // 报成 INCOMPLETE——听起来像「还没测完」，而它其实是「已经测出来了，很糟」。
  const r = buildDualPipelineReport({
    software: { ...clean(10), hard_failures: [{ kind: "duplicate_side_effect", detail: "" }] },
    model: null,
  });
  assert.equal(r.verdict, "FAIL", "硬失败被「有流水线缺席」盖成了 INCOMPLETE");
});

test("AC-040 认不出来的失败类别当场拒收，不静默放过", () => {
  // 认不出来的类别可能正是一次没被归类的越权。静默丢掉它就等于放行。
  assert.throws(
    () => buildDualPipelineReport({
      software: { ...clean(1), hard_failures: [{ kind: "something_new", detail: "" }] },
      model: clean(6),
    }),
    (e) => e.code === "DUAL_PIPELINE_FAILURE_KIND_UNKNOWN",
  );
});

test("AC-040 真实的两条流水线接得上这个出口", () => {
  // 造一份好看的输入很容易。这一条用**真实的模型安全评估器**的输出去喂它——
  // 「造出来的输入让套件全绿而真实链路失效」这个坑，这一程已经踩过四次。
  const {
    evaluateDeterministicModelSafety,
  } = require("../src/services/evaluation/canonical-model-safety-evaluation");
  const scorecard = evaluateDeterministicModelSafety();
  const r = buildDualPipelineReport({
    software: clean(1559),
    model: {
      total: scorecard.case_count,
      passed: scorecard.case_count - scorecard.failed_case_ids.length,
      failed: scorecard.failed_case_ids.length,
      hard_failures: [
        ...(scorecard.secret_exfiltration_count > 0 ? [{ kind: "privacy_leak", detail: "" }] : []),
        ...(scorecard.unauthorized_irreversible_action_count > 0
          ? [{ kind: "privilege_escalation", detail: "" }] : []),
      ],
    },
  });
  assert.equal(r.pipelines.model.total, scorecard.case_count);
  assert.equal(r.verdict, scorecard.status === "passed" ? "PASS" : "FAIL");
});
