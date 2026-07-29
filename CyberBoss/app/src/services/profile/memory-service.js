"use strict";

// 长期记忆的**写**那一侧。
//
// profile_facts 这张表和 SqliteProfileStore 一直都在，但线上没有任何地方往里
// 写过一个字——后台那栏和个人主页那栏因此永远是空的。「代码在不等于功能在」，
// 这是同一个病的第十次。
//
// 只让模型记 explicit（他自己说过的），不让它记 inferred（它猜的）：
//   · inferred 在 profile-projector 里要求 sourceRef + evidenceRef + confidence
//     + counterevidence 四样齐全才存得下，模型给不出可信的那四样；
//   · 更重要的是，猜出来的东西会被当成事实反复用在后面每一轮对话里。记错一件
//     事，比不记这件事糟得多——主人会发现它"记得的我"不是他。
//
// 敏感类目（profile-projector 里的 SENSITIVE_CATEGORIES）走不到这里：那一层
// 要求 explicitSensitiveConsent 精确等于类目名，这个服务不传，所以必然被拒。
// 这是有意的——那类信息不该由一次闲聊顺手记下来。

const CATEGORIES = Object.freeze([
  "basic",
  "preference",
  "routine",
  "goal",
  "relationship",
  "work",
  "interest",
  "communication_style",
]);

class MemoryServiceError extends Error {
  constructor(code) {
    super(code);
    this.name = "MemoryServiceError";
    this.code = code;
  }
}

class MemoryService {
  // store 和 resolveUserId 由上层注入。user_id 是服务器从发件人推出来的，
  // **绝不能**让模型在参数里指定——它想记到谁头上就记到谁头上的话，隔离就没了。
  constructor({ store = null, resolveUserId = null } = {}) {
    this.store = store;
    this.resolveUserId = resolveUserId;
  }

  #userId(context) {
    const resolved = typeof this.resolveUserId === "function"
      ? String(this.resolveUserId(context) || "").trim()
      : "";
    if (!resolved) {
      throw new MemoryServiceError("MEMORY_USER_UNKNOWN");
    }
    return resolved;
  }

  #store() {
    if (!this.store) {
      throw new MemoryServiceError("MEMORY_STORE_UNAVAILABLE");
    }
    return this.store;
  }

  remember({ category = "", key = "", value = "" } = {}, context = {}) {
    const userId = this.#userId(context);
    if (!CATEGORIES.includes(category)) {
      throw new MemoryServiceError("MEMORY_CATEGORY_INVALID");
    }
    // key 是这件事的名字（sleep / hometown / job），要稳定：同一件事再说一次
    // 应该覆盖旧的，而不是并排堆两条。
    const factKey = String(key || "").trim().toLowerCase();
    if (!/^[a-z][a-z0-9_]{0,39}$/.test(factKey)) {
      throw new MemoryServiceError("MEMORY_KEY_INVALID");
    }
    const text = String(value || "").trim();
    if (!text || text.length > 300) {
      throw new MemoryServiceError("MEMORY_VALUE_INVALID");
    }
    return this.#store().suggest({
      userId,
      category,
      factKey,
      value: text,
      // 只记他自己说过的。
      kind: "explicit",
    });
  }

  recall(_args, context = {}) {
    const userId = this.#userId(context);
    const projection = this.#store().projection(userId);
    const facts = [];
    for (const [category, entries] of Object.entries(projection?.facts || {})) {
      for (const [key, value] of Object.entries(entries || {})) {
        facts.push({
          category,
          key,
          value: typeof value === "string" ? value : JSON.stringify(value),
        });
      }
    }
    return facts;
  }
}

module.exports = { CATEGORIES, MemoryService, MemoryServiceError };
