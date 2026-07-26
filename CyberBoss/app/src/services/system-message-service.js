const crypto = require("crypto");

const { resolveSelectedAccount } = require("../adapters/channel/weixin/account-store");
const { loadPersistedContextTokens } = require("../adapters/channel/weixin/context-token-store");
const { resolvePreferredSenderId, resolvePreferredWorkspaceRoot } = require("../core/default-targets");
const { SystemMessageQueueStore } = require("../core/system-message-queue-store");

class SystemMessageService {
  constructor({ config, sessionStore }) {
    this.config = config;
    this.sessionStore = sessionStore;
    this.queue = new SystemMessageQueueStore({ filePath: config.systemMessageQueueFile });
  }

  queueMessage({ text = "", userId = "", workspaceRoot = "" } = {}, context = {}) {
    const normalizedText = normalizeText(text);
    if (!normalizedText) {
      throw new Error("system send requires text");
    }

    const account = resolveSelectedAccount(this.config);
    const senderId = normalizeText(userId)
      || normalizeText(context?.senderId)
      || resolvePreferredSenderId({
        config: this.config,
        accountId: account.accountId,
        sessionStore: this.sessionStore,
      });
    const resolvedWorkspaceRoot = normalizeText(workspaceRoot)
      || normalizeText(context?.workspaceRoot)
      || resolvePreferredWorkspaceRoot({
        config: this.config,
        accountId: account.accountId,
        senderId,
        sessionStore: this.sessionStore,
      });

    if (!senderId || !resolvedWorkspaceRoot) {
      throw new Error("system send requires a sender and workspace");
    }
    const workspace = this.config.workspaceRegistry.assertAllowedRoot(resolvedWorkspaceRoot);

    const contextTokens = loadPersistedContextTokens(this.config, account.accountId);
    if (!contextTokens[senderId]) {
      throw new Error(`Cannot find a context token for user ${senderId}. Let this user talk to the bot once first.`);
    }

    return this.queue.enqueue({
      id: crypto.randomUUID(),
      accountId: account.accountId,
      senderId,
      workspaceRoot: workspace.root,
      text: normalizedText,
      createdAt: new Date().toISOString(),
    });
  }
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

module.exports = { SystemMessageService };
