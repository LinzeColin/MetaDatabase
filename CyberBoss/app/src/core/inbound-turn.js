const {
  STICKER_DESC_GUIDANCE,
  STICKER_TAG_GUIDANCE,
} = require("../services/sticker-service");
const { injectedTimeLine } = require("../services/time/canonical-time");

function buildInboundDraft(normalized, { attachments = [], attachmentFailures = [] } = {}) {
  const originalText = normalizeText(normalized?.text);
  return {
    ...normalized,
    originalText,
    text: originalText,
    attachments: Array.isArray(attachments) ? attachments : [],
    attachmentFailures: Array.isArray(attachmentFailures) ? attachmentFailures : [],
  };
}

function buildMergedInboundPrepared({
  bindingKey,
  workspaceRoot,
  messages = [],
  trailingPrepared = null,
}) {
  const queued = Array.isArray(messages) ? messages.filter((message) => message && typeof message === "object") : [];
  const latest = trailingPrepared || queued[queued.length - 1] || {};
  const originalTexts = queued
    .map((message) => normalizeText(message.originalText))
    .filter(Boolean);
  const trailingText = normalizeText(trailingPrepared?.originalText);
  if (trailingText) {
    originalTexts.push(trailingText);
  }
  const attachments = queued.flatMap((message) => Array.isArray(message.attachments) ? message.attachments : []);
  const attachmentFailures = queued.flatMap((message) => Array.isArray(message.attachmentFailures) ? message.attachmentFailures : []);
  const originalText = originalTexts.join("\n\n");

  return {
    bindingKey,
    workspaceRoot,
    ...latest,
    originalText,
    text: originalText,
    attachments,
    attachmentFailures,
  };
}

function assembleRuntimeTurnText({
  prepared,
  config = {},
  visionContext = {},
  personaInstruction = "",
  // 这个人的 IANA 时区。缺就按北京时间渲染——今天所有人都走这条回退，因为写
  // user_location_profiles 的信号采集在 CB9-210/220。参数先留着，是为了让填它
  // 的那个节点只需要改一处调用，而不用再动这里的渲染逻辑。
  userZone = "",
}) {
  const lines = [];
  // 语气块贴在最前面，早于时间戳和用户原话。放在末尾会被长附件段落推远，模型
  // 更容易忽略它；放最前面则每一轮都先读到"该怎么说话"。
  const persona = normalizeText(personaInstruction);
  if (persona) {
    lines.push(persona);
  }
  const localTime = formatWechatLocalTime(prepared?.receivedAt, userZone);
  const originalText = normalizeText(prepared?.originalText ?? prepared?.text);
  const attachments = Array.isArray(prepared?.attachments) ? prepared.attachments : [];
  const attachmentFailures = Array.isArray(prepared?.attachmentFailures) ? prepared.attachmentFailures : [];
  const imageAttachments = attachments.filter((item) => isImageAttachmentItem(item));
  const visualItems = Array.isArray(visionContext.items) ? visionContext.items : [];
  const visionErrors = Array.isArray(visionContext.errors) ? visionContext.errors : [];

  if (localTime) {
    if (lines.length) {
      lines.push("");
    }
    // 时区要写出来。这个时刻是东八区的，但模型的开场白由 codex 生成，它照抄
    // 宿主机时区——机器是 UTC 的时候那里写着 <timezone>UTC</timezone>。一个不
    // 带时区的时刻加一句"你在 UTC"，模型就会把它当 UTC 再换算，主人在悉尼 0 点
    // 问它答"悉尼时间 8 点"。TZ=Asia/Shanghai 已经在部署里设上了，这行是第二道
    // 闸：万一哪天 codex 是被手工拉起来的、没继承到 TZ，时刻本身仍然自证时区。
    //
    // 括号里那句从 canonical-time 出：这个人有当地时区就写成「当地时间…（北京
    // 时间…）」，没有就还是单独一个北京时间（CB9-200 / AC-041）。
    lines.push(localTime);
  }
  if (originalText) {
    if (lines.length) {
      lines.push("");
    }
    lines.push(originalText);
  }

  if (attachments.length) {
    pushSectionBreak(lines);
    lines.push("Saved attachments:");
    for (const item of attachments) {
      const suffix = item.sourceFileName ? ` (original name: ${item.sourceFileName})` : "";
      lines.push(`- [${item.kind || "attachment"}] ${item.absolutePath}${suffix}`);
    }
    lines.push("Use the saved local files if they are needed for the request.");
  }

  if (visualItems.length) {
    pushSectionBreak(lines);
    lines.push("Visual context from attachments:");
    for (const item of visualItems) {
      const source = normalizeText(item.absolutePath) || normalizeText(item.sourceFileName) || "image";
      lines.push(`- ${source}: ${normalizeText(item.description)}`);
    }
  }

  if (imageAttachments.length) {
    pushSectionBreak(lines);
    lines.push(`If some images are reusable stickers, load \`cyberboss_sticker_tags\` only when needed. ${STICKER_TAG_GUIDANCE}`);
    lines.push(`To save reusable stickers, call \`cyberboss_sticker_save_from_inbox\` once with an \`items\` array. Use 1-3 tags. ${STICKER_DESC_GUIDANCE} Skip ordinary photos, screenshots, and unclear images.`);
    lines.push("Do not describe save steps. The system sends the sticker notice.");
  }

  if (attachmentFailures.length || visionErrors.length) {
    pushSectionBreak(lines);
    lines.push("Attachment intake errors:");
    for (const item of attachmentFailures) {
      const label = item.sourceFileName || item.kind || "attachment";
      lines.push(`- ${label}: ${item.reason}`);
    }
    for (const item of visionErrors) {
      const label = item.absolutePath || item.sourceFileName || item.kind || "image";
      lines.push(`- ${label}: ${item.reason}`);
    }
  }

  return lines.join("\n").trim();
}

function shouldBatchImageOnlyInbound(message) {
  const originalText = normalizeText(message?.originalText);
  const attachments = Array.isArray(message?.attachments) ? message.attachments : [];
  const attachmentFailures = Array.isArray(message?.attachmentFailures) ? message.attachmentFailures : [];
  return !originalText
    && attachments.length > 0
    && attachments.every((item) => isImageAttachmentItem(item))
    && attachmentFailures.length === 0;
}

function takeImageOnlyBatchMessages(messages, maxAttachments) {
  const batchMessages = [];
  const remainingMessages = [];
  let remainingCapacity = Math.max(1, Number(maxAttachments) || 1);

  for (const message of Array.isArray(messages) ? messages : []) {
    const attachments = Array.isArray(message?.attachments) ? message.attachments : [];
    if (!attachments.length) {
      continue;
    }
    if (remainingCapacity <= 0) {
      remainingMessages.push(message);
      continue;
    }
    if (attachments.length <= remainingCapacity) {
      batchMessages.push(message);
      remainingCapacity -= attachments.length;
      continue;
    }
    batchMessages.push({
      ...message,
      attachments: attachments.slice(0, remainingCapacity),
    });
    remainingMessages.push({
      ...message,
      attachments: attachments.slice(remainingCapacity),
    });
    remainingCapacity = 0;
  }

  return {
    batchMessages,
    remainingMessages,
  };
}

function clonePreparedInboundMessage(prepared) {
  return {
    workspaceId: prepared.workspaceId,
    accountId: prepared.accountId,
    senderId: prepared.senderId,
    messageId: prepared.messageId,
    traceId: prepared.traceId,
    contextToken: prepared.contextToken,
    provider: prepared.provider,
    originalText: prepared.originalText,
    text: prepared.text,
    attachments: Array.isArray(prepared.attachments) ? prepared.attachments : [],
    attachmentFailures: Array.isArray(prepared.attachmentFailures) ? prepared.attachmentFailures : [],
    receivedAt: prepared.receivedAt,
  };
}

function isPlainTextPreparedMessage(prepared) {
  const originalText = normalizeText(prepared?.originalText);
  const attachments = Array.isArray(prepared?.attachments) ? prepared.attachments : [];
  const attachmentFailures = Array.isArray(prepared?.attachmentFailures) ? prepared.attachmentFailures : [];
  return Boolean(originalText) && attachments.length === 0 && attachmentFailures.length === 0;
}

function isImageAttachmentItem(item) {
  return Boolean(item?.isImage) || normalizeText(item?.contentType).toLowerCase().startsWith("image/")
    || normalizeText(item?.kind).toLowerCase() === "image";
}

function pushSectionBreak(lines) {
  if (lines.length) {
    lines.push("");
  }
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

// 时区口径统一由 canonical-time 出（CB9-200）。这里只负责「拿不到时刻就不写
// 那一行」——认不出来的字符串原样返回，交给上面判空。
function formatWechatLocalTime(receivedAt, userZone) {
  const value = typeof receivedAt === "string" ? receivedAt.trim() : "";
  if (!value) {
    return "";
  }
  return injectedTimeLine(value, userZone) || value;
}

module.exports = {
  assembleRuntimeTurnText,
  buildInboundDraft,
  buildMergedInboundPrepared,
  clonePreparedInboundMessage,
  isImageAttachmentItem,
  isPlainTextPreparedMessage,
  shouldBatchImageOnlyInbound,
  takeImageOnlyBatchMessages,
};
