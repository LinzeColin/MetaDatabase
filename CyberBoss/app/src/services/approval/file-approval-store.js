"use strict";

// 审批台账的落盘（CB9-440 / AC-021）。
//
// 台账必须熬过重启：只存内存的话，重启即失忆，用户会被要求再批一次；而他多半
// 以为第一次没生效，于是又批一次——两次副作用。
//
// **每次 transact 都重新从盘上读**，不用内存缓存。理由是这个进程不是唯一的写
// 者：轮询器、portal 和主循环都可能碰它。缓存一份的话，两个写者各自基于一份
// 过期的快照做决定，而「重复批准不产生重复副作用」正是靠看到对方的写入实现的。
//
// 写用「先写临时文件再 rename」：rename 在同一个文件系统上是原子的，所以任何
// 时刻盘上要么是旧的完整内容，要么是新的完整内容，不会有一个写了一半的台账。
// 直接覆写的话，进程在写到一半时崩掉，整个台账就成了半截 JSON——而那时候恰恰
// 是最需要它的时候。

const fs = require("node:fs");
const path = require("node:path");

class FileApprovalStore {
  constructor({ filePath }) {
    if (typeof filePath !== "string" || !filePath.trim()) {
      throw new TypeError("filePath required");
    }
    this.filePath = filePath;
  }

  #load() {
    try {
      const raw = fs.readFileSync(this.filePath, "utf8");
      const parsed = JSON.parse(raw);
      const rows = new Map();
      for (const record of Array.isArray(parsed?.approvals) ? parsed.approvals : []) {
        if (record && typeof record.request_id === "string") {
          rows.set(record.request_id, Object.freeze(record));
        }
      }
      return rows;
    } catch {
      // 文件不在、空的、或者坏了 —— 都从空台账开始。
      //
      // 坏了也当空的是有意的：一个读不出来的台账和没有台账，对「这件事批过没
      // 有」这个问题给出同一个答案（不知道），而不知道时正确的做法是**当没批
      // 过**——让用户再批一次，而不是当批过了直接执行。
      return new Map();
    }
  }

  #save(rows) {
    const dir = path.dirname(this.filePath);
    fs.mkdirSync(dir, { recursive: true });
    const payload = JSON.stringify({
      version: 1,
      approvals: [...rows.values()],
    }, null, 2);
    const temp = `${this.filePath}.${process.pid}.tmp`;
    fs.writeFileSync(temp, payload, "utf8");
    // 原子替换。崩在这一行之前盘上是旧的完整内容，之后是新的完整内容。
    fs.renameSync(temp, this.filePath);
  }

  // 读—改—写一次做完。
  //
  // 这不是真正的跨进程锁（那需要 flock 或者数据库），但它把窗口压到最小：
  // 读和写之间没有任何 await。真正的并发保护在 CB9-450 的幂等键上——两条
  // 防线，这一条挡的是同一个进程里的交错。
  transact(mutator) {
    const rows = this.#load();
    const before = rows.size;
    const snapshot = new Map(rows);
    const result = mutator(rows);
    // 没改就不写。写的话每次读都会产生一次文件变更，而备份和同步跟着涨。
    const changed = rows.size !== before
      || [...rows.entries()].some(([key, value]) => snapshot.get(key) !== value);
    if (changed) {
      this.#save(rows);
    }
    return result;
  }
}

// 测试和本地跑用。行为和落盘那份一致，只是不落盘。
class MemoryApprovalStore {
  constructor() {
    this.rows = new Map();
  }

  transact(mutator) {
    return mutator(this.rows);
  }
}

module.exports = { FileApprovalStore, MemoryApprovalStore };
