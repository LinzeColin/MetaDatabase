import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const css = fs.readFileSync(new URL("../src/ui/styles.css", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/ui/app.js", import.meta.url), "utf8");
const pages = fs.readFileSync(new URL("../src/core/public-pages.js", import.meta.url), "utf8");

test("移动端正文不低于 16px 且主动作可触控", () => {
  assert.match(css, /@media \(max-width: 430px\)[\s\S]*body \{ font-size: 16px; \}/);
  assert.match(css, /\.hero-actions \.button \{ width: 100%; min-height: 48px; \}/);
  assert.match(css, /\.button \{[\s\S]*min-height: 46px/);
});

test("键盘、减少动态效果与高对比模式有明确合同", () => {
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /prefers-contrast: more/);
  assert.match(css, /forced-colors: active/);
  assert.match(app, /class="skip-link"/);
});

test("手机状态页用卡片矩阵而不是 980px 横向表格", () => {
  assert.match(css, /business-governance tbody td:nth-of-type\(5\)::before/);
  assert.match(css, /business-table-wrap \{ overflow: visible/);
  assert.match(pages, /端到端白箱治理矩阵/);
  assert.match(pages, /依赖与耦合/);
  assert.match(pages, /验收 Oracle/);
});
