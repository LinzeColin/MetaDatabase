#!/usr/bin/env node

const { main } = require("../src/index");
const { explainError } = require("../src/core/friendly-errors");

main().catch((error) => {
  // 用户看到的是"发生了什么 + 现在做什么"，原始错误始终保留在最后一行。
  console.error(explainError(error));
  process.exitCode = 1;
});
