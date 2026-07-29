"use strict";

// 一条消息要发给某个人的时候，得先知道「这个人挂在哪个号下面」。
//
// 每个人扫码都会生成一个属于他自己的 bot 号，所以 senderId 和 accountId 是
// 多对一的：拿错号去发，微信会告诉你 context_token 不认识——那是必然的，
// context_token 本来就是某个号和某个人之间的凭据。
//
// 归属关系不需要另存一张表：context_token 文件本身就是按号分开存的，
// 谁的 token 在哪个文件里，谁就挂在那个号下面。这是真实发生过的事实记录，
// 不是推断。
//
// 这个模块单独拆出来，是因为 account-store 不能 require context-token-store
// ——后者在模块顶层 require 前者取 normalizeAccountId，两边互相 require 会让
// 先加载的一方拿到半个空对象。

const { listActiveAccounts, pickPrimaryAccount, resolveSelectedAccount } = require("./account-store");
const { loadPersistedContextTokens } = require("./context-token-store");

function normalizeUserId(value) {
  return typeof value === "string" ? value.trim() : "";
}

// 返回 { accountId -> Set(senderId) } 的反向索引：senderId -> accountId。
function buildSenderIndex(config, accounts = null) {
  const list = Array.isArray(accounts) ? accounts : listActiveAccounts(config);
  const index = new Map();
  for (const account of list) {
    const tokens = loadPersistedContextTokens(config, account.accountId);
    for (const senderId of Object.keys(tokens)) {
      // 先写入的优先。同一个人同时出现在两个号下面只可能是残留，
      // 而残留的那个号迟早会被 cleanupStaleAccountsForUserId 清掉。
      if (!index.has(senderId)) {
        index.set(senderId, account.accountId);
      }
    }
  }
  return index;
}

// 找不到归属时退回主号，而不是抛错：新用户的第一条回复是在
// rememberContextToken 落盘之后才发的，中间那一瞬间索引里确实还没有他。
// 这时退回主号至少能把话发出去；真发错了，微信会用 context_token 挡下来，
// 比在这里抛一个「找不到号」把整条回复吃掉要好。
function resolveAccountForUser(config, userId) {
  const accounts = listActiveAccounts(config);
  if (!accounts.length) {
    // 让 resolveSelectedAccount 抛出那两句分得清的中文错误。
    return resolveSelectedAccount(config);
  }
  const normalized = normalizeUserId(userId);
  if (normalized) {
    for (const account of accounts) {
      if (loadPersistedContextTokens(config, account.accountId)[normalized]) {
        return account;
      }
    }
  }
  return pickPrimaryAccount(config, accounts);
}

module.exports = {
  buildSenderIndex,
  resolveAccountForUser,
};
