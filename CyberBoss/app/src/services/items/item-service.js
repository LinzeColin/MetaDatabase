"use strict";

// 让模型也能记待办和日程。
//
// 「记一下 买菜」那条确定性口令是**下限**：保证最普通的说法一定不落空。但真
// 秘书不该只认口令——「这周五之前把房租交了」「明天下午三点那个会你记一下」
// 这种话只有模型听得懂，它得有地方把听懂的东西放进去。
//
// 两条路写的是同一张表，所以微信里记的和聊天里记的会出现在同一个列表上，
// 主人不用去想"我刚才是用哪种方式记的"。

class ItemServiceError extends Error {
  constructor(code) {
    super(code);
    this.name = "ItemServiceError";
    this.code = code;
  }
}

class ItemService {
  // resolveUserId 由上层注入：user_id 是服务器从发件人推出来的，**绝不能**让
  // 模型在参数里指定。它想给谁记就给谁记的话，隔离就没了。
  constructor({ database = null, resolveUserId = null } = {}) {
    this.database = database;
    this.resolveUserId = resolveUserId;
  }

  #userId(context) {
    const resolved = typeof this.resolveUserId === "function"
      ? String(this.resolveUserId(context) || "").trim()
      : "";
    if (!resolved) {
      throw new ItemServiceError("ITEM_USER_UNKNOWN");
    }
    return resolved;
  }

  #database() {
    if (!this.database) {
      throw new ItemServiceError("ITEM_STORE_UNAVAILABLE");
    }
    return this.database;
  }

  async add({ title = "", note = "", dueAt = "", kind = "todo" } = {}, context = {}) {
    const userId = this.#userId(context);
    return this.#database().createUserItem({
      userId,
      kind: kind === "event" ? "event" : "todo",
      title,
      note,
      // 模型没给时间就是没有截止时间。这里不替它补一个——补出来的时刻会让主人
      // 在莫名其妙的时候被提醒，而他从没说过那个时间。
      dueAt: String(dueAt || "").trim() || null,
    });
  }

  async list({ kind = "todo" } = {}, context = {}) {
    const userId = this.#userId(context);
    return this.#database()
      .listUserItems({ userId, kind: kind === "event" ? "event" : "todo", open: true })
      // 只回模型需要的三样。id 和密文一个都不给出去。
      .map((item) => ({ title: item.title, dueAt: item.dueAt, createdAt: item.createdAt }));
  }
}

module.exports = { ItemService, ItemServiceError };
