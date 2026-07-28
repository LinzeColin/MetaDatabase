"use strict";

// 仓库里到底有没有这个程序的全部源码？
//
// 这套测试存在的理由：`.gitignore` 里一条没锚定的 `runtime/` 规则，把
// app/src/services/runtime/ 下八个源文件全吞了——公平队列、预算守卫、断路器、
// 模型运行时控制器，一次都没进过任何提交。而 525 个测试全绿，因为测试跑在
// 文件确实躺在磁盘上的工作树里；一个新克隆出来的仓库是坏的。
//
// 所以：不能只测"代码对不对"，还要测"代码在不在仓库里"。

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const APP = path.join(__dirname, "..");
const PROJECT = path.join(APP, "..");

function git(args) {
  return execFileSync("git", ["-C", PROJECT, ...args], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
}

function repositoryAvailable() {
  try {
    git(["rev-parse", "--git-dir"]);
    return true;
  } catch {
    return false;
  }
}

// 程序真正要用到的源文件目录。node_modules 和生成物不在其中。
const SOURCE_ROOTS = ["app/src", "app/bin", "app/test", "app/migrations", "app/templates", "ops", "scripts"];
const SOURCE_EXTENSIONS = new Set([".js", ".cjs", ".mjs", ".py", ".sql", ".html", ".json", ".css"]);

function walk(directory, out = []) {
  if (!fs.existsSync(directory)) {
    return out;
  }
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) {
      continue;
    }
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      walk(full, out);
    } else if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      out.push(full);
    }
  }
  return out;
}

test("磁盘上的每一个源文件都在仓库里", (t) => {
  if (!repositoryAvailable()) {
    t.skip("不在 git 仓库里运行");
    return;
  }
  const tracked = new Set(
    git(["ls-files"]).split("\n").filter(Boolean).map((line) => path.join(PROJECT, line)),
  );

  const missing = [];
  for (const root of SOURCE_ROOTS) {
    for (const file of walk(path.join(PROJECT, root))) {
      if (!tracked.has(file)) {
        missing.push(path.relative(PROJECT, file));
      }
    }
  }

  assert.deepEqual(
    missing,
    [],
    `这些源文件在磁盘上有、但仓库里没有——新克隆出来会缺件：\n  ${missing.join("\n  ")}`,
  );
});

test("忽略规则不会再吞掉源码目录", (t) => {
  if (!repositoryAvailable()) {
    t.skip("不在 git 仓库里运行");
    return;
  }
  // check-ignore 是 git 自己的判定，比我重新解释一遍 .gitignore 语法可靠。
  const sourceFiles = SOURCE_ROOTS.flatMap((root) => walk(path.join(PROJECT, root)))
    .map((file) => path.relative(PROJECT, file));
  assert.ok(sourceFiles.length > 100, "应该扫到相当数量的源文件");

  let ignored = "";
  try {
    ignored = execFileSync("git", ["-C", PROJECT, "check-ignore", "--stdin"], {
      input: sourceFiles.join("\n"),
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch (error) {
    // 一个都没被忽略时 check-ignore 的退出码是 1，这正是我们想要的结果。
    if (error.status !== 1) {
      throw error;
    }
    ignored = "";
  }

  assert.equal(
    ignored.trim(),
    "",
    `.gitignore 正在忽略源文件：\n  ${ignored.trim().split("\n").join("\n  ")}`,
  );
});

test("忽略规则锚定到项目根，不匹配任意深度的同名目录", () => {
  const rules = fs
    .readFileSync(path.join(PROJECT, ".gitignore"), "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));

  // 这几个词在源码树里也是正当目录名，所以它们的规则必须锚定。
  const mustBeAnchored = ["runtime", "work", "tmp", "dist"];
  for (const name of mustBeAnchored) {
    const unanchored = rules.filter(
      (rule) => rule === `${name}/` || rule === name,
    );
    assert.deepEqual(
      unanchored,
      [],
      `"${name}" 的忽略规则没有锚定，会匹配任意深度的同名目录——`
        + `请写成 /${name}/ 或加上具体路径`,
    );
  }
});

test("package.json 的 files 字段不会漏掉运行必需的目录", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(APP, "package.json"), "utf8"));
  if (!manifest.files) {
    // 没有 files 字段就是全都带上，这也是安全的。
    return;
  }
  for (const required of ["src", "bin", "templates", "migrations"]) {
    assert.ok(
      manifest.files.some((entry) => entry === required || entry.startsWith(`${required}/`)),
      `package.json 的 files 里缺 ${required}，npm 打包出来会少东西`,
    );
  }
});
