import test from "node:test";
import assert from "node:assert/strict";
import { buildBookSkill } from "../src/core/book-to-skill.js";
import { testPlatform } from "./service/helpers.mjs";

const PASSWORD = "Correct-Horse-2026";

test("Book-to-Skill 从单本笔记提炼结构，不把整本笔记原文当作输出", () => {
  const artifact = buildBookSkill({
    bookTitle: "系统思维", author: "作者甲", generatedAt: "2026-07-29T00:00:00.000Z",
    notes: [
      { title: "反馈回路框架", content: "系统由增强回路和调节回路共同塑造。" },
      { title: "行动练习", content: "先画出因果链，再用小实验验证假设。" },
      { title: "常见误区", content: "避免只追逐短期指标，否则会忽略滞后效应。" },
    ],
  });
  assert.equal(artifact.kind, "reading-book-skill");
  assert.equal(artifact.source.noteCount, 3);
  assert.ok(artifact.skill.frameworks.length >= 1);
  assert.ok(artifact.skill.techniques.length >= 1);
  assert.ok(artifact.skill.antiPatterns.length >= 1);
  assert.match(artifact.markdown, /# 《系统思维》 · 作者甲 阅读 Skill/u);
  assert.equal(artifact.markdown.includes("系统由增强回路和调节回路共同塑造"), true);
  assert.equal(artifact.filename.endsWith(".md"), true);
});

test("Book-to-Skill 以账户级加密对象保存，可导出、删除且不跨租户泄漏", async t => {
  const platform = testPlatform();
  t.after(platform.close);
  const user = await platform.service.registerPassword({ email: "skill-owner@example.com", password: PASSWORD, displayName: "Skill 用户" });
  const other = await platform.service.registerPassword({ email: "skill-other@example.com", password: PASSWORD, displayName: "其他用户" });
  await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "skill-1", title: "反馈回路", content: "系统由增强回路和调节回路共同塑造。", bookTitle: "系统思维", author: "作者甲" });
  await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "skill-2", title: "行动练习", content: "先画出因果链，再用小实验验证假设。", bookTitle: "系统思维", author: "作者甲" });
  await platform.service.saveDocument(user.account.id, { source: "manual", externalId: "other-book", title: "其他书", content: "这一条不得进入目标 Skill。", bookTitle: "另一册", author: "作者乙" });

  const preview = await platform.service.previewBookSkill(user.account.id, { bookTitle: "系统思维", author: "作者甲" });
  assert.equal(preview.preview.source.noteCount, 2);
  assert.equal(preview.preview.artifact.markdown.includes("这一条不得进入目标 Skill"), false);

  const saved = await platform.service.saveBookSkill(user.account.id, { bookTitle: "系统思维", author: "作者甲" });
  assert.match(saved.bookSkill.id, /^skill_/u);
  const raw = platform.store.db.prepare("SELECT object_key AS objectKey FROM book_skills WHERE id=?").get(saved.bookSkill.id);
  const encrypted = await platform.objectStore.get(raw.objectKey);
  assert.ok(encrypted);
  assert.equal(encrypted.bytes.toString("utf8").includes("增强回路"), false);
  const read = await platform.service.readBookSkill(user.account.id, saved.bookSkill.id);
  assert.match(read.artifact.markdown, /反馈回路/u);
  assert.equal(await platform.service.readBookSkill(other.account.id, saved.bookSkill.id), null);

  const exported = await platform.service.exportAccount(user.account.id);
  assert.equal(exported.bookSkills.length, 1);
  assert.match(exported.bookSkills[0].artifact.markdown, /系统思维/u);
  assert.equal(JSON.stringify(exported).includes("objectKey"), false);

  const deleted = await platform.service.deleteBookSkill(user.account.id, saved.bookSkill.id);
  assert.equal(deleted.deleted, true);
  assert.equal(await platform.objectStore.get(raw.objectKey), null);
});
