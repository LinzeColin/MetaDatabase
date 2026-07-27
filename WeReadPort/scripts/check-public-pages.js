import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expectedPublicPages } from "./generate-public-pages.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const errors = [];
for (const [route, expected] of Object.entries(expectedPublicPages())) {
  const file = path.join(root, route, "index.html");
  let actual;
  try {
    actual = await readFile(file, "utf8");
  } catch {
    errors.push(`${route}/index.html 不存在。`);
    continue;
  }
  if (actual !== expected) errors.push(`${route}/index.html 与单一内容源不一致；请运行 npm run generate:public。`);
  if (!actual.includes("<main")) errors.push(`${route}/index.html 缺少无需 JavaScript 即可读取的正文。`);
}
if (errors.length) {
  console.error("公开静态页面检查失败：");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
console.log("公开静态页面检查通过：隐私、条款与系统状态均由单一内容源生成且无需 JavaScript 即可阅读。");
