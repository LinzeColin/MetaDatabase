"use strict";

// AC-014 explicitly reuses the OpenAI-compatible implementation for DeepSeek
// rather than forking it. This module names that relationship so a future
// OpenAI-compatible provider extends the same code path with its own policy.

const { DeepSeekAdapter } = require("./deepseek");

module.exports = { DeepSeekAdapter, OpenAICompatibleAdapter: DeepSeekAdapter };
