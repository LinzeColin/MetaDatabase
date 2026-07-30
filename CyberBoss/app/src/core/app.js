const path = require("path");
const crypto = require("crypto");
const fs = require("fs");
const { createWeixinChannelAdapter } = require("../adapters/channel/weixin");
const { DEFAULT_MIN_WEIXIN_CHUNK, MAX_MIN_WEIXIN_CHUNK } = require("../adapters/channel/weixin/config-store");
const { persistIncomingWeixinAttachments } = require("../adapters/channel/weixin/media-receive");
const { createCodexRuntimeAdapter } = require("../adapters/runtime/codex");
const { createClaudeCodeRuntimeAdapter } = require("../adapters/runtime/claudecode");
const { findModelByQuery } = require("../adapters/runtime/codex/model-catalog");
const { createTimelineIntegration } = require("../integrations/timeline");
const {
  assembleRuntimeTurnText,
  buildInboundDraft,
  buildMergedInboundPrepared,
  clonePreparedInboundMessage,
  isPlainTextPreparedMessage,
  shouldBatchImageOnlyInbound,
  takeImageOnlyBatchMessages,
} = require("./inbound-turn");
const { resolveVisionContext } = require("../services/vision-context");
const {
  buildWeixinHelpText,
} = require("./command-registry");
const { CheckinConfigStore, parseCheckinRangeMinutes, resolveDefaultCheckinRange } = require("./checkin-config-store");
const { resolvePreferredSenderId, resolvePreferredWorkspaceRoot } = require("./default-targets");
const { StreamDelivery } = require("./stream-delivery");
const { WalkingSkeletonTraceStore } = require("./walking-skeleton-trace");
const { ThreadStateStore } = require("./thread-state-store");
const { DeferredSystemReplyStore } = require("./deferred-system-reply-store");
const { SystemMessageQueueStore } = require("./system-message-queue-store");
const { SystemMessageDispatcher } = require("./system-message-dispatcher");
const { TimelineScreenshotQueueStore } = require("./timeline-screenshot-queue-store");
const { TurnGateStore } = require("./turn-gate-store");
const { ReminderQueueStore } = require("../adapters/channel/weixin/reminder-queue-store");
const {
  buildConfirmation,
  buildDueMessage,
  parseReminderIntent,
} = require("../services/reminder/reminder-intent");
const {
  buildAddedMessage,
  buildDoneFailedMessage,
  buildDoneMessage,
  buildListMessage,
  parseItemIntent,
} = require("../services/items/item-intent");
const { SqliteProfileStore } = require("../services/profile/profile-store");
const {
  buildAlertMessage,
  buildRecoveryMessage,
  diffFindings,
  evaluateHealth,
} = require("../services/health/self-check");
const { MIGRATIONS, RuntimeSpoolDatabase } = require("../services/db/database-adapter");
const { resolveAccountForUser } = require("../adapters/channel/weixin/account-routing");
const {
  CanonicalSpoolCoordinator,
} = require("../services/canonical/canonical-sync");
const { DurableInboxCoordinator } = require("../services/inbox/durable-inbox");
const { JobScheduler } = require("../services/jobs/job-scheduler");
const {
  DurableOutboxWorker,
} = require("../services/outbox/durable-outbox");
const {
  ResourceReadinessGate,
  captureLiveResourceSnapshot,
} = require("../services/jobs/resource-readiness-gate");
const {
  matchesCommandPrefix,
  canonicalizeCommandTokens,
  extractApprovalFilePaths,
  isPathWithinRoot,
  normalizeCommandTokens,
  splitCommandLine,
} = require("../adapters/runtime/shared/approval-command");
const { updateEnvFile } = require("./bootstrap");
const { UserAdmissionService } = require("./user-admission");
const { DEFAULT_PROVIDER_POLICIES, UserTurnRuntime } = require("./user-turn-runtime");
const { UserCompanionTurn } = require("./user-companion-turn");
const { BackupRunner } = require("../services/backup/backup-runner");
const { projectLiveStatus } = require("../services/status/live-status-projector");
const {
  PersonaStore,
  TONE_PRESETS,
  LENGTH_PRESETS,
  MAX_ALLOWED_MINUTES,
  MAX_SEATS,
  MIN_ALLOWED_MINUTES,
  MAX_NOTE_CHARS,
  renderPersonaInstruction,
} = require("../services/persona/persona-store");
const {
  MAX_TTL_MS: SESSION_MAX_TTL_MS,
  SqliteSessionTokenService,
  parseSessionCookie,
} = require("../services/security/session-token-service");
const { SqliteAdminLoginTickets } = require("../services/security/admin-login-ticket");
const { renderQrSvg, svgDataUri } = require("../v8-prebuilt/public-entry/qr-svg");
const { loadRuntimeTextSecret } = require("../v8-prebuilt/security/runtime-text-secret");
const { SetupPortal } = require("../services/portal/setup-portal");
const { buildPortalHandlers } = require("../services/portal/portal-handlers");
const { PortalHttpServer } = require("../services/portal/portal-server");
const { runSystemCheckinPoller } = require("../app/system-checkin-poller");
const { createProjectTooling } = require("../tools/create-project-tooling");
const { WorkspaceRegistryError } = require("./workspace-registry");
const DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000;
const MIN_LONG_POLL_TIMEOUT_MS = 2_000;
const SESSION_EXPIRED_ERRCODE = -14;
const RETRY_DELAY_MS = 2_000;
const BACKOFF_DELAY_MS = 30_000;
const MAX_CONSECUTIVE_FAILURES = 3;
// 一条主动消息最多重排几次。见 requeueSystemMessage：无限重排会让一个号哑掉。
const SYSTEM_MESSAGE_MAX_ATTEMPTS = 5;
const MAX_INBOUND_STICKER_IMAGE_BATCH = 10;
const INBOUND_IMAGE_BATCH_IDLE_MS = 1_500;
// 公开入口的限流。/join 没有鉴权（刻意的），但每次出码都会真的打一次 iLink，
// 所以对外调用的次数必须被我自己发出去的票数封死。
const PUBLIC_QR_MIN_INTERVAL_MS = 1_500;
const PUBLIC_QR_MAX_PENDING = 20;
// iLink 的授权码本身大约 5 分钟过期，这里留一点余量再弃。
const PUBLIC_QR_TICKET_TTL_MS = 6 * 60_000;

const OWNER_CLAIMED_NOTICE = [
  "认出你了，你是这里的主人 ✓",
  "",
  "可以直接跟我说话。想让朋友也能用，发「邀请」就行。",
  "随时可以发「帮助」看看还能做什么。",
].join("\n");

// Status 的业务线名字对普通人来说是黑话，这里给出人话版。
const PLAIN_LINE_NAMES = Object.freeze({
  wechat_channel: "微信通道",
  user_registration_consent: "开通流程",
  user_isolation: "用户隔离",
  secure_setup_portal: "设置页面",
  ai_provider_connection: "AI 连接",
  four_source_import: "聊天记录导入",
  profile_memory: "资料与记忆",
  timeline_diary_reminder: "时间线与提醒",
  canonical_sync: "数据归档",
  r2_oci_objects: "云端存储",
  backup_restore: "备份与恢复",
  owner_codex_runtime: "主人的开发助手",
  release_rollback: "发布与回滚",
  model_usage_budget_circuit: "用量与限额",
});

// 后台会话有效期，取 session 服务允许的上限（24 小时）。
//
// 这个上限是那个模块自己的安全属性，不为后台单独放宽——/setup 的用户会话用的
// 是同一张表同一套代码。取而代之的是**续期**：页面每次打开都拿现有会话换一张
// 新的（见 issueAdminSession 的 renew 分支），所以常用的那台设备永远不会掉线，
// 而放着不用的会话 24 小时后自己失效。真掉了也只是在微信里发一句「后台」。
const ADMIN_SESSION_TTL_MS = SESSION_MAX_TTL_MS;

// 后台「对话」一栏用的人话标签。出站队列的状态码原样显示等于没显示。
const OUTBOX_STATE_LABELS = Object.freeze({
  pending: "排队中",
  sending: "发送中",
  retry: "发送失败，正在重试",
  confirmed: "已送达",
  failed_terminal: "发送失败，已放弃",
});

// 把后台传来的日期变成能和 received_at（ISO UTC）直接比大小的字符串。
//
// 主人在手机上只会填「2026-07-28」这种。光标补 T00:00:00Z 会漏掉当天的消息，
// 所以结束边界补到当天最后一毫秒。填了完整 ISO 就原样用。填得不合法一律返回
// 空串——宁可不筛，也不能悄悄筛成一个错误的范围让人以为"这段时间没说过话"。
function isoBound(value, edge) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return edge === "end" ? `${text}T23:59:59.999Z` : `${text}T00:00:00.000Z`;
  }
  const parsed = new Date(text);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString() : "";
}

// 一条来信最终怎么了。stuck 为 true 表示"人发了但没得到答复"——去掉自动回执
// 之后，这是唯一能看出这件事的地方，所以它必须判得准，不能一律显示成功。
function describeTurnState({ message, job, replies }) {
  const delivered = replies.some((reply) => reply.delivered && reply.kind !== "accepted");
  if (delivered) {
    return Object.freeze({ label: "已回复", tone: "ok", stuck: false });
  }
  if (message.status === "rejected") {
    // handled_by_admission 是准入层当场办掉的（入门引导、状态、口令），不是错误。
    return message.rejectReason === "handled_by_admission"
      ? Object.freeze({ label: "已当场答复", tone: "ok", stuck: false })
      : Object.freeze({ label: `没有收下：${message.rejectReason || "未说明"}`, tone: "bad", stuck: true });
  }
  if (job && ["failed_terminal", "reply_failed", "expired", "cancelled", "rejected"].includes(job.status)) {
    return Object.freeze({
      label: `没答上：${job.errorClass || job.status}`,
      tone: "bad",
      stuck: true,
    });
  }
  if (replies.length) {
    // 判"发不出去"看的是队列状态，不是有没有错误码——投递失败时 last_error_class
    // 可能是空的，只看错误码会把一条彻底放弃的回复显示成"正在回复"。
    const failed = replies.find((reply) => reply.rawStatus === "failed_terminal");
    if (failed) {
      return Object.freeze({
        label: failed.error ? `回复发不出去：${failed.error}` : "回复发不出去",
        tone: "bad",
        stuck: true,
      });
    }
    return Object.freeze({ label: "正在回复", tone: "wait", stuck: false });
  }
  if (job && ["succeeded", "replied", "canonical_synced", "canonical_pending"].includes(job.status)) {
    // 任务成了却没有任何一条出站消息——这是个真问题，不能显示成"已回复"。
    return Object.freeze({ label: "想好了但没发出来", tone: "bad", stuck: true });
  }
  return Object.freeze({ label: "正在处理", tone: "wait", stuck: false });
}

const PLAIN_RESOURCE_REASONS = Object.freeze({
  MIN_FREE_MEMORY: "内存不太够了",
  MIN_FREE_DISK: "磁盘快满了",
  MIN_FREE_INODES: "磁盘的文件数量到上限了",
  MAX_QUEUE_DEPTH: "排队的活儿有点多",
  MAX_LOAD_RATIO: "CPU 比较忙",
  METRIC_MISSING: "有项指标没测到，为安全起见先不接新活",
});

function requireAbsoluteRuntimePath(value, label) {
  if (typeof value !== "string" || !path.isAbsolute(value)) {
    throw new Error(`${label}_ABSOLUTE_REQUIRED`);
  }
  return value;
}

function readOwnerOnlyRuntimeKey(filePath, label) {
  const absolute = requireAbsoluteRuntimePath(filePath, `${label}_FILE`);
  let stat;
  try {
    stat = fs.lstatSync(absolute);
  } catch {
    throw new Error(`${label}_UNAVAILABLE`);
  }
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new Error(`${label}_FILE_INVALID`);
  }
  if ((stat.mode & 0o077) !== 0) {
    throw new Error(`${label}_PERMISSIONS_INVALID`);
  }
  if (stat.size !== 32) {
    throw new Error(`${label}_LENGTH_INVALID`);
  }
  const key = fs.readFileSync(absolute);
  if (key.length !== 32) {
    key.fill(0);
    throw new Error(`${label}_LENGTH_INVALID`);
  }
  return key;
}

function resolveActivePayloadTtlMs(hours) {
  if (!Number.isSafeInteger(hours) || hours < 1 || hours > 168) {
    throw new Error("ACTIVE_PAYLOAD_TTL_HOURS_INVALID");
  }
  return hours * 60 * 60 * 1000;
}

// 把配置里指定的模型并进服务端白名单。
//
// 白名单的意义是「用户不能自己指定 model 和 origin」——那条边界照旧。这里加的
// 是**运营者**在部署时配的那一个，等价于改一次常量，只是不用重新发版。
//
// 不这么做的话，CB_OWNER_MODEL_OPENAI 填了一个新模型，assertModel 会以
// MODEL_NOT_ALLOWED 把每一轮都挡掉，而面板上只会显示"AI 服务暂时不可用"。
function buildProviderPolicies(config) {
  const merged = {};
  for (const [providerId, policy] of Object.entries(DEFAULT_PROVIDER_POLICIES)) {
    const extra = providerId === "openai"
      ? String(config?.ownerModelOpenAI || "").trim()
      : providerId === "deepseek"
        ? String(config?.ownerModelDeepSeek || "").trim()
        : "";
    merged[providerId] = Object.freeze({
      ...policy,
      models: Object.freeze(
        extra && !policy.models.includes(extra)
          ? [...policy.models, extra]
          : [...policy.models],
      ),
    });
  }
  return Object.freeze(merged);
}

function createRuntimeAdapter(config) {
  if (config.runtime === "claudecode") {
    return createClaudeCodeRuntimeAdapter(config);
  }
  return createCodexRuntimeAdapter(config);
}

class CyberbossApp {
  constructor(config) {
    this.config = config;
    if (!config?.workspaceRegistry) {
      throw new Error("workspace registry is required");
    }
    this.workspaceRegistry = config.workspaceRegistry;
    this.channelAdapter = createWeixinChannelAdapter(config);
    this.timelineIntegration = createTimelineIntegration(config);
    const projectTooling = createProjectTooling(config, {
      channelAdapter: this.channelAdapter,
      timelineIntegration: this.timelineIntegration,
      // 待办和日程的库，以及"这一轮是谁"。
      //
      // 用 getter 而不是直接传值：库是 start() 之后才打开的，构造这一刻还是 null。
      // 传死的话工具永远拿到 null，又是一个"代码在但功能不在"。
      get itemDatabase() {
        return null;
      },
      resolveItemUserId: (context) => this.resolveUserIdForToolCall(context),
    });
    // 库要等 start() 打开之后才有，这里补上引用。
    Object.defineProperty(projectTooling.services.items, "database", {
      get: () => this.runtimeSpoolDatabase,
      configurable: true,
    });
    Object.defineProperty(projectTooling.services.memory, "store", {
      get: () => this.profileStoreOrNull(),
      configurable: true,
    });
    this.projectServices = projectTooling.services;
    this.projectToolHost = projectTooling.toolHost;
    this.runtimeContextStore = projectTooling.runtimeContextStore;
    this.runtimeAdapter = createRuntimeAdapter(config);
    this.threadStateStore = new ThreadStateStore();
    this.systemMessageQueue = new SystemMessageQueueStore({ filePath: config.systemMessageQueueFile });
    this.deferredSystemReplyQueue = new DeferredSystemReplyStore({ filePath: config.deferredSystemReplyQueueFile });
    this.checkinConfigStore = new CheckinConfigStore({ filePath: config.checkinConfigFile });
    this.timelineScreenshotQueue = new TimelineScreenshotQueueStore({ filePath: config.timelineScreenshotQueueFile });
    this.reminderQueue = new ReminderQueueStore({ filePath: config.reminderQueueFile });
    this.turnGateStore = new TurnGateStore();
    this.pendingInboundByScope = new Map();
    this.pendingImageInboundByScope = new Map();
    this.turnBoundaryScopeKeys = new Set();
    this.systemMessageDispatcher = null;
    this.walkingSkeletonTrace = new WalkingSkeletonTraceStore({
      filePath: config.walkingSkeletonTraceFile,
      stateDir: config.stateDir,
    });
    this.streamDelivery = new StreamDelivery({
      channelAdapter: this.channelAdapter,
      sessionStore: this.runtimeAdapter.getSessionStore(),
      runtimeId: this.runtimeAdapter.describe().id,
      onDeferredSystemReply: (payload) => this.deferSystemReply(payload),
      onTraceEvent: (event) => this.walkingSkeletonTrace.record(event),
      // 不经过 outbox 的那条路（主动打招呼、到点提醒、入门引导）在这里记账，
      // 否则后台「对话」栏永远看不见机器人自己主动说过什么。
      onDirectDelivery: (entry) => this.noteBotInitiated(entry),
      // 主动打招呼连着几次决定不说话。体检那一层用它认出"在空转烧额度"。
      onSystemReplySilent: () => { this.checkinSilentStreak += 1; },
      onSystemReplySent: () => { this.checkinSilentStreak = 0; },
    });
    // 空转计数。只活在内存里是对的：重启之后从头数，不会拿着上一个进程的
    // 旧账去打扰主人。
    this.checkinSilentStreak = 0;
    this.lastHealthReport = null;
    this.lastHealthCheckAt = 0;
    this.pendingOperationByRunKey = new Map();
    this.runtimeEventChain = Promise.resolve();
    this.runtimeSpoolDatabase = null;
    this.durableInboxCoordinator = null;
    // 一个号一个协调器。游标、context_token、bot token 全是按号分开的，
    // 共用一个会让第二个号的消息被第一个号的游标当成"收过了"直接跳过。
    this.durableInboxCoordinators = new Map();
    this.accountPollsInFlight = new Map();
    this.accountPollFailureCounts = new Map();
    // 公开入口发出去的授权码票据：ticket -> 出票时刻。
    this.publicEntryGate = { lastMintedAt: 0, tickets: new Map() };
    this.jobScheduler = null;
    this.outboxWorker = null;
    this.canonicalSyncCoordinator = null;
    this.userAdmission = null;
    this.userTurnRuntime = null;
    this.userCompanionTurn = null;
    this.backupRunner = null;
    this.personaStore = null;
    this.setupPortal = null;
    this.portalServer = null;
    this.runtimeRestartTimestamps = [];
    this.runtimeAdapter.onEvent((event) => {
      // 每一轮的执行轨迹。在这之前这些事件只在内存里流过去就没了，主人在后台
      // 看不到"它当时到底在干什么"——一轮慢了、失败了，唯一的线索是一个错误码。
      this.noteTurnTrace(event);
      this.threadStateStore.applyRuntimeEvent(event);
      this.runtimeEventChain = this.runtimeEventChain
        .catch(() => {})
        .then(() => this.handleRuntimeEvent(event))
        .catch((error) => {
          const message = error instanceof Error ? error.stack || error.message : String(error);
          console.error(`[cyberboss] runtime event handling failed type=${event?.type || "(unknown)"} ${message}`);
        });
    });
  }

  initializeDurableInbox() {
    if (this.config.durableInbox !== true) {
      if (
        this.config.durableInbox === false
        && this.config.baselineStagingAllowed !== true
      ) {
        throw new Error("DURABLE_INBOX_BASELINE_FALLBACK_FORBIDDEN");
      }
      return;
    }
    if (this.runtimeSpoolDatabase || this.durableInboxCoordinator) {
      throw new Error("DURABLE_INBOX_ALREADY_INITIALIZED");
    }
    const encryptionKey = readOwnerOnlyRuntimeKey(
      this.config.runtimeEncryptionKeyFile,
      "RUNTIME_ENCRYPTION_KEY",
    );
    const identityKey = readOwnerOnlyRuntimeKey(
      this.config.runtimeIdentityKeyFile,
      "RUNTIME_IDENTITY_KEY",
    );
    try {
      this.runtimeSpoolDatabase = new RuntimeSpoolDatabase({
        databasePath: requireAbsoluteRuntimePath(
          this.config.runtimeDatabasePath,
          "RUNTIME_DATABASE_PATH",
        ),
        encryptionKey,
        identityKey,
        payloadTtlMs: resolveActivePayloadTtlMs(
          this.config.activePayloadTtlHours,
        ),
      });
      // 语气设置。放在 multiUser 判断之外：单人跑的时候也该能调语气。
      this.personaStore = new PersonaStore({
        database: this.runtimeSpoolDatabase,
        // 取函数不取值：库刚开，ownerUserId 这一刻可能还没 backfill 完。
        ownerUserId: () => this.ownerUserId(),
      });
      // The v0.0.0.8 admission anchor. It is built here because this is the one
      // place where the runtime database is open and both owner-only keys are
      // still live; they are zeroed in the finally below.
      if (this.config.multiUser === true) {
        this.userAdmission = new UserAdmissionService({
          database: this.runtimeSpoolDatabase.database,
          identityKey,
          ownerUserId: this.runtimeSpoolDatabase.ownerUserId,
          ownerSenderIds: this.config.ownerSenderIds || this.config.allowedUserIds,
          registrationMode: this.resolveRegistrationMode(),
          portalOrigin: this.config.portalOrigin || "",
          seatLimitProvider: () => this.resolveSeatLimit(),
          // 「初始不需要任何设置，不需要回复同意并开始」。告知照发，但不挡路。
          requireExplicitConsent: this.config.requireExplicitConsent === true,
        });
        this.userCompanionTurn = new UserCompanionTurn({
          database: this.runtimeSpoolDatabase.database,
          // 少了这一行，「别再问我」写进去的还是那张没人读的表。
          personaStore: this.personaStore,
        });
        this.backupRunner = new BackupRunner({
          databasePath: this.config.runtimeDatabasePath,
          encryptionKey,
          stateDir: this.config.stateDir,
          config: this.config,
        });
        this.userTurnRuntime = new UserTurnRuntime({
          database: this.runtimeSpoolDatabase.database,
          userRepository: this.userAdmission.users,
          encryptionKey,
          // 配置里指定的模型必须进白名单，否则 assertModel 会把它挡掉——
          // 「配了新模型，结果每个人都收不到回复」。白名单本身仍然是服务端
          // 拥有的：用户永远不能自己指定 model 或 origin，只能在这份里挑。
          providerPolicies: buildProviderPolicies(this.config),
          // 前 N 个开通的人用主人的额度；第 N+1 个开始必须自己填密钥。
          ownerQuota: {
            resolve: (userId) => this.resolveOwnerQuotaFor(userId),
            // 席位还有没有。有的话，这个人不该被推去填密钥——那不是他的事。
            seatAvailable: (userId) => this.ownerSeatAvailableFor(userId),
          },
          ...(Number.isSafeInteger(this.config.userTurnTimeoutMs)
            ? { requestTimeoutMs: this.config.userTurnTimeoutMs }
            : {}),
        });
        // 必须排在 userTurnRuntime 之后：portal 的 handlers 要用它的 vault 和
        // policies。之前放在前面，于是只要配了域名，构造就抛
        // "Cannot read properties of null (reading 'vault')"——而没配域名的机器
        // 永远走不到这一行，所以本机怎么跑都看不出问题。
        if (this.config.portalOrigin) {
          this.setupPortal = new SetupPortal({
            database: this.runtimeSpoolDatabase.database,
            allowedOrigins: [this.config.portalOrigin],
            userRepository: this.userAdmission.users,
            handlers: buildPortalHandlers({
              database: this.runtimeSpoolDatabase.database,
              vault: this.userTurnRuntime.vault,
              userRepository: this.userAdmission.users,
              providerPolicies: this.userTurnRuntime.policies,
            }),
          });
        }
      }
      if (this.config.durableOutbox === true) {
        this.outboxWorker = new DurableOutboxWorker({
          database: this.runtimeSpoolDatabase,
          channelAdapter: this.channelAdapter,
          leaseMs: this.config.outboxLeaseMs,
          maxAttempts: this.config.outboxMaxAttempts,
          baseDelayMs: this.config.outboxBaseDelayMs,
          maxDelayMs: this.config.outboxMaxDelayMs,
          maxChunkChars: this.config.outboxChunkChars,
        });
        this.streamDelivery.setOutboxWorker(this.outboxWorker);
      }
      if (this.config.canonicalSync === true) {
        this.canonicalSyncCoordinator = new CanonicalSpoolCoordinator({
          database: this.runtimeSpoolDatabase,
          outgoingDirectory: path.join(
            this.config.canonicalSpoolRoot,
            "outgoing",
          ),
          receiptDirectory: path.join(
            this.config.canonicalSpoolRoot,
            "receipts",
          ),
          quarantineDirectory: path.join(
            this.config.canonicalSpoolRoot,
            "quarantine",
          ),
          deployedCommit: this.config.canonicalDeployedCommit,
          maxRecords: this.config.canonicalBatchMax,
          maxBytes: this.config.canonicalBatchMaxBytes,
          maxAgeMs: this.config.canonicalBatchMaxAgeMs,
          flushOnTerminal: this.config.canonicalMaterialFlush,
          materialEventTypes: this.config.canonicalMaterialEventTypes,
          ordinarySyncOnCalendar: this.config.canonicalOrdinarySyncOnCalendar,
          backlogMaxEvents: this.config.canonicalBacklogMaxEvents,
          backlogMaxBytes: this.config.canonicalBacklogMaxBytes,
          maxLagSeconds: this.config.canonicalMaxLagSeconds,
        });
      }
      this.durableInboxCoordinator = this.buildInboxCoordinator(this.channelAdapter);
      if (this.config.jobScheduler === true) {
        const gate = new ResourceReadinessGate({
          pollStaleMs: this.config.pollStaleMs,
          queueStuckMs: this.config.queueStuckMs,
          queueLimit: this.config.schedulerQueueLimit,
        });
        this.jobScheduler = new JobScheduler({
          database: this.runtimeSpoolDatabase,
          workspaceRegistry: this.workspaceRegistry,
          gate,
          runtimeLeaseMs: this.config.runtimeLeaseMs,
          controlLeaseMs: this.config.controlLeaseMs,
          runtimeReadiness: () => (
            typeof this.runtimeAdapter.getReadiness === "function"
              ? this.runtimeAdapter.getReadiness()
              : { ready: false, reason: "runtime_readiness_unavailable" }
          ),
          snapshotProvider: (facts) => captureLiveResourceSnapshot(facts),
          dispatchRuntime: (payload) => this.dispatchDurableRuntimeJob(payload),
          dispatchControl: (payload) => this.dispatchDurableControlJob(payload),
          onRuntimeTerminal: (payload) => (
            payload?.event
              ? undefined
              : this.handleDurableJobTerminal(payload)
          ),
          canonicalMutationGuard: () => (
            this.canonicalSyncCoordinator
              ? this.canonicalSyncCoordinator.mutationGuard()
              : {
                  mutationAllowed: false,
                  reason: "canonical_coordinator_unavailable",
                }
          ),
        });
      }
    } catch (error) {
      this.closeDurableInbox();
      throw error;
    } finally {
      encryptionKey.fill(0);
      identityKey.fill(0);
    }
  }

  // 一个号一个协调器，形状完全一样，只是钉死在不同的号上。
  // channelAdapterView 要么是整个适配器（主号），要么是 forAccount(id) 的单号视图。
  buildInboxCoordinator(channelAdapterView) {
    return new DurableInboxCoordinator({
      channelAdapter: channelAdapterView,
      database: this.runtimeSpoolDatabase,
      config: this.config,
      // 在建 job 之前分流。非主人的三条路（入门回复、普通用户确定性口令、
      // 席位已满的拒绝）到了调度阶段就没有出口了——JobScheduler 要求
      // dispatchRuntime 返回真实的 threadId/turnId，等于强制走一次模型。
      admissionFilter: (normalized) => this.admissionHandledBeforeJob(normalized),
      // 这条消息记在谁名下。不给的话数据库一律记到主人名下——所有人的每一条
      // 消息都会落进主人的隔离域。只有一个人在用的时候看不出来。
      resolveUserId: (normalized) => this.scopeUserIdForInbound(normalized),
      // 收下消息**不回执**，但要记一件事：这个人的 context_token。
      //
      // 不回执的理由：人不会先说一句"收到，正在处理"再回答。真实的"我在听"
      // 信号是微信自己的"对方正在输入"——dispatchPreparedTurn 里已经发了
      // sendTyping。代价是答复失败就彻底安静，所以可见性移到了后台「对话」栏。
      //
      // 记 context_token 的理由（这是个真实故障，不是保险）：
      // 主动打招呼、提醒到点、任何系统消息，都要靠 senderId 反查 context_token
      // 才能发回微信，而它们查的是 channelAdapter 的那份缓存。往那份缓存里写的
      // 只有 rememberBaselineStagingContextTokens，**而它只在非 durable 那条
      // 分支上被调用**——线上跑的是 durable 这条，于是缓存永远是空的：
      //   · cyberboss_reminder_create 一律抛 "Let this user talk to the bot
      //     once first"，哪怕这个人刚说完话
      //   · 主动打招呼能唤醒模型，但答复没有投递目标，发不出去
      // 收下消息这一刻是唯一同时握着 senderId 和 context_token 的地方。
      //
      // normalized.accountId 是**这条消息从哪个号收到的**，必须一起传：
      // 不传就会落到主号名下，之后给这个人回信会拿主号的 token 去发，必被拒。
      onAccepted: ({ normalized }) => {
        try {
          this.channelAdapter.rememberContextToken?.(
            normalized.senderId,
            normalized.contextToken,
            normalized.accountId,
          );
        } catch {
          // 记不住不该让这条消息进不来；最坏结果是主动消息暂时发不出去。
        }
      },
    });
  }

  // 盘上现在有哪些号，各自的协调器。每一轮桥接循环调一次：
  // 有人刚扫完码，下一轮就被收进来，不用重启服务。
  liveInboxCoordinators() {
    if (!this.durableInboxCoordinator) {
      return [];
    }
    const accounts = typeof this.channelAdapter.listAccounts === "function"
      ? this.channelAdapter.listAccounts()
      : [this.channelAdapter.resolveAccount()];
    const live = [];
    const seen = new Set();
    for (const account of accounts) {
      const accountId = String(account?.accountId || "").trim();
      if (!accountId || seen.has(accountId)) {
        continue;
      }
      seen.add(accountId);
      let coordinator = this.durableInboxCoordinators.get(accountId);
      if (!coordinator) {
        coordinator = accountId === this.activeAccountId
            || typeof this.channelAdapter.forAccount !== "function"
          ? this.durableInboxCoordinator
          : this.buildInboxCoordinator(this.channelAdapter.forAccount(accountId));
        this.durableInboxCoordinators.set(accountId, coordinator);
      }
      live.push({ accountId, coordinator });
    }
    // 号被删掉之后它的协调器也该丢掉，否则会一直拿着一个作废的 token 去拉更新。
    for (const accountId of Array.from(this.durableInboxCoordinators.keys())) {
      if (!seen.has(accountId)) {
        this.durableInboxCoordinators.delete(accountId);
      }
    }
    return live;
  }

  // 每个号一条独立的长轮询，谁先回来就先处理谁。
  //
  // 不能等齐：一次长轮询要挂到 35 秒，等最慢的那个回来再跑调度，等于给每一条
  // 回复凭空加最多 35 秒延迟——号越多越慢。
  //
  // 已经在飞的那条不重发：同一个号同时开两条 get_updates，两条会拿着同一个
  // 起始游标各收一批，提交的时候互相覆盖，中间那批消息就永远丢了。
  //
  // 只有一个号的时候，这个函数的行为和以前那行 `await coordinator.pollOnce()`
  // 完全一样：发一条、等它、收它。
  async pollAccountsOnce({ timeoutMs } = {}) {
    const live = this.liveInboxCoordinators();
    const liveIds = new Set(live.map((entry) => entry.accountId));
    for (const accountId of Array.from(this.accountPollsInFlight.keys())) {
      if (!liveIds.has(accountId)) {
        // 号被删了就别再等它那条了，否则循环会一直挂在一个不会有结果的请求上。
        this.accountPollsInFlight.delete(accountId);
      }
    }
    for (const { accountId, coordinator } of live) {
      if (this.accountPollsInFlight.has(accountId)) {
        continue;
      }
      const record = { accountId, settled: false, result: null };
      record.promise = coordinator.pollOnce({ timeoutMs }).then(
        (durable) => {
          record.settled = true;
          record.result = { accountId, durable };
          return record;
        },
        (error) => {
          record.settled = true;
          record.result = { accountId, error };
          return record;
        },
      );
      this.accountPollsInFlight.set(accountId, record);
    }
    if (!this.accountPollsInFlight.size) {
      return [];
    }
    await Promise.race(
      Array.from(this.accountPollsInFlight.values(), (record) => record.promise),
    );
    const harvested = [];
    for (const [accountId, record] of this.accountPollsInFlight) {
      if (record.settled) {
        harvested.push(record.result);
        this.accountPollsInFlight.delete(accountId);
      }
    }
    return harvested;
  }

  // 这一轮各个号的结果该怎么看。
  //
  // 最要紧的一条：**只有主人的号过期才是致命的**。主人的号断了，整个服务确实
  // 没法工作，必须停下来让他重新扫码；但访客的号过期只影响那一个人，不能因为
  // 某个陌生人的绑定失效就把所有人的机器人一起关掉——那正是「一个人挂了全体
  // 陪葬」，多号最容易犯的错。
  classifyPollResults(results) {
    const failures = [];
    const successes = [];
    let ownerSessionExpired = false;
    for (const result of Array.isArray(results) ? results : []) {
      if (result?.error) {
        failures.push(result);
        if (
          result.accountId === this.activeAccountId
          && isSessionExpiredError(result.error)
        ) {
          ownerSessionExpired = true;
        }
        continue;
      }
      if (result?.durable) {
        successes.push(result);
      }
    }
    return Object.freeze({
      successes,
      failures,
      anyOk: successes.length > 0,
      ownerSessionExpired,
      // 全挂了才往外抛：还有一个号活着就继续跑，不退避。
      allFailedError: !successes.length && failures.length ? failures[0].error : null,
    });
  }

  // 一个号一直拉不动的时候，日志不能每 35 秒刷一条——那会把 journal 撑爆，
  // 也会把真正的问题埋掉。第一次必报，之后每 20 次报一次。
  noteAccountPollFailure(accountId, error) {
    const count = (this.accountPollFailureCounts.get(accountId) || 0) + 1;
    this.accountPollFailureCounts.set(accountId, count);
    if (count === 1 || count % 20 === 0) {
      console.error(
        `[cyberboss] poll failed account=${accountId} (第 ${count} 次) ${formatErrorMessage(error)}`,
      );
    }
  }

  // 现在归这个进程管的所有号。
  liveAccountIds() {
    try {
      const accounts = typeof this.channelAdapter.listAccounts === "function"
        ? this.channelAdapter.listAccounts()
        : [this.channelAdapter.resolveAccount()];
      const ids = accounts.map((account) => String(account?.accountId || "").trim()).filter(Boolean);
      return ids.length ? ids : [this.activeAccountId].filter(Boolean);
    } catch {
      return [this.activeAccountId].filter(Boolean);
    }
  }

  closeDurableInbox() {
    if (this.jobScheduler) {
      this.jobScheduler.stop();
      this.jobScheduler = null;
    }
    if (this.outboxWorker) {
      this.outboxWorker.stop();
      this.outboxWorker = null;
      this.streamDelivery.setOutboxWorker(null);
    }
    if (this.canonicalSyncCoordinator) {
      this.canonicalSyncCoordinator.stop();
      this.canonicalSyncCoordinator = null;
    }
    this.durableInboxCoordinator = null;
    this.durableInboxCoordinators.clear();
    this.userAdmission = null;
    this.userTurnRuntime = null;
    this.userCompanionTurn = null;
    this.backupRunner = null;
    this.personaStore = null;
    this.setupPortal = null;
    if (this.runtimeSpoolDatabase) {
      this.runtimeSpoolDatabase.close();
      this.runtimeSpoolDatabase = null;
    }
  }

  printDoctor() {
    console.log(JSON.stringify({
      stateDir: this.config.stateDir,
      channel: this.channelAdapter.describe(),
      runtime: this.runtimeAdapter.describe(),
      timeline: this.timelineIntegration.describe(),
      threads: this.threadStateStore.snapshot(),
      operations: this.projectOperationalStatus(),
    }, null, 2));
  }

  // CB-810 on the live process: the frozen business matrix, resource gate and
  // self-heal policy, fed by this process's own measurements. It carries counts
  // and states only — no user identifier ever reaches Status.
  projectOperationalStatus() {
    try {
      return projectLiveStatus({
        facts: this.collectStatusFacts(),
        restartHistory: this.runtimeRestartTimestamps || [],
        ...this.collectModelUsageRows(),
      });
    } catch (error) {
      // A projection that cannot be built is reported as a projection failure,
      // never as a healthy matrix.
      return Object.freeze({
        status: null,
        error_code: normalizeErrorCode(error?.code) || "status_projection_failed",
      });
    }
  }

  // Usage and circuit rows for AC-048, aggregated by provider. The SQL sums
  // across users so no per-user row ever leaves the database for Status.
  collectModelUsageRows() {
    if (!this.runtimeSpoolDatabase) {
      return { usageRows: [], circuitRows: [] };
    }
    try {
      return {
        usageRows: this.runtimeSpoolDatabase.database
          .prepare(
            `SELECT provider_id AS providerId,
                    SUM(reserved_tokens) AS reservedTokens,
                    SUM(charged_tokens) AS chargedTokens
             FROM model_token_usage_daily
             GROUP BY provider_id`,
          )
          .all()
          .map((row) => ({
            providerId: row.providerId,
            reservedTokens: Number(row.reservedTokens) || 0,
            chargedTokens: Number(row.chargedTokens) || 0,
          })),
        circuitRows: this.runtimeSpoolDatabase.database
          .prepare(
            `SELECT provider_id AS providerId, state
             FROM provider_circuits
             WHERE scope='global'`,
          )
          .all()
          .map((row) => ({ providerId: row.providerId, state: row.state })),
      };
    } catch {
      // A counter that cannot be read is omitted, never guessed at.
      return { usageRows: [], circuitRows: [] };
    }
  }

  collectStatusFacts() {
    const runtimeReadiness = typeof this.runtimeAdapter.getReadiness === "function"
      ? this.runtimeAdapter.getReadiness()
      : { ready: false };
    let activeUsers = 0;
    let providersConfigured = 0;
    if (this.runtimeSpoolDatabase) {
      try {
        activeUsers = Number(this.runtimeSpoolDatabase.database
          .prepare("SELECT COUNT(*) AS count FROM users WHERE status='active'")
          .get().count);
        providersConfigured = Number(this.runtimeSpoolDatabase.database
          .prepare("SELECT COUNT(*) AS count FROM provider_credentials WHERE status='active'")
          .get().count);
      } catch {
        // A counter that cannot be read stays zero; it is never guessed.
      }
    }
    const canonicalStatus = this.canonicalSyncCoordinator
      ? this.canonicalSyncCoordinator.status()
      : null;
    return {
      channelReady: Boolean(this.activeAccountId),
      admissionEnabled: Boolean(this.userAdmission),
      activeUsers,
      // 服务真的在监听才算挂上了；只是把对象 new 出来不算。
      portalMounted: Boolean(this.portalServer),
      providersConfigured,
      importsReady: Boolean(this.projectServices),
      profileReady: Boolean(this.runtimeSpoolDatabase),
      timelineReady: Boolean(this.timelineIntegration),
      canonicalReady: Boolean(this.canonicalSyncCoordinator),
      canonicalQueueDepth: Number(canonicalStatus?.pending || 0),
      objectStoreConfigured: this.backupRunner?.status().ready === true,
      backupConfigured: this.backupRunner?.status().ready === true,
      ownerRuntimeReady: runtimeReadiness?.ready === true,
      releaseConfigured: false,
      budgetReady: Boolean(this.userTurnRuntime),
    };
  }

  // 扫码登录的那个微信号，本身就是主人。
  //
  // 这条必须优先于「第一个发消息的人是主人」。很多人是拿自己的常用微信登录的，
  // 那样他没法给自己发消息，而"第一个发消息的人"会变成第一个来找他聊天的朋友
  // ——朋友就拿到了 Owner 权限。所以只要登录信息里带着账号自己的身份，就用它，
  // 认领窗口一秒都不开。
  bindOwnerFromAccount(account) {
    const selfId = normalizeText(account?.userId);
    if (!selfId) {
      // 老版本登录没存这个字段。此时才退回认领窗口，并且明说。
      console.warn(
        "[cyberboss] 这次登录没有带回账号自己的微信标识，"
        + "所以主人要靠「第一个发消息的人」来认领。"
        + "如果这个号是你自己的常用微信，请先运行 cyberboss login 重新扫一次码。",
      );
      return null;
    }
    const configured = Array.isArray(this.config.ownerSenderIds)
      ? this.config.ownerSenderIds.filter(Boolean)
      : [];
    if (configured.length) {
      return configured;
    }
    this.config.ownerSenderIds = [selfId];
    this.rememberOwnerSender(selfId);
    console.log(
      "[cyberboss] 主人 = 扫码登录的这个微信号本身。"
      + "别人给它发消息都是普通用户，要邀请码才能开通。",
    );
    return this.config.ownerSenderIds;
  }

  async login() {
    await this.channelAdapter.login();
  }

  printAccounts() {
    this.channelAdapter.printAccounts();
  }

  async start() {
    const account = this.channelAdapter.resolveAccount();
    this.activeAccountId = account.accountId;
    // 必须在 initializeDurableInbox 之前：admission 服务是在那里用
    // ownerSenderIds 构造的。
    this.bindOwnerFromAccount(account);
    this.systemMessageDispatcher = new SystemMessageDispatcher({
      queueStore: this.systemMessageQueue,
      config: this.config,
      accountId: account.accountId,
    });
    let runtimeState;
    try {
      this.initializeDurableInbox();
      runtimeState = await this.runtimeAdapter.initialize();
      await this.outboxWorker?.start();
      await this.canonicalSyncCoordinator?.start();
      await this.startPortalServer();
      this.jobScheduler?.start();
    } catch (error) {
      this.closeDurableInbox();
      await this.runtimeAdapter.close().catch(() => {});
      throw error;
    }
    const knownContextTokens = Object.keys(this.channelAdapter.getKnownContextTokens()).length;
    const syncBuffer = this.channelAdapter.loadSyncBuffer();
    await this.restoreBoundThreadSubscriptions();
    await this.jobScheduler?.runCycle();

    console.log("[cyberboss] bootstrap ok");
    console.log(`[cyberboss] channel=${this.channelAdapter.describe().id}`);
    console.log(`[cyberboss] runtime=${this.runtimeAdapter.describe().id}`);
    console.log(`[cyberboss] timeline=${this.timelineIntegration.describe().id}`);
    const managedAccounts = this.liveAccountIds();
    console.log(`[cyberboss] account=${account.accountId}（主号）`);
    console.log(`[cyberboss] accounts=${managedAccounts.length} ${managedAccounts.join(",")}`);
    console.log(`[cyberboss] baseUrl=${account.baseUrl}`);
    console.log(`[cyberboss] workspaceRoot=${this.config.workspaceRoot}`);
    console.log(`[cyberboss] knownContextTokens=${knownContextTokens}`);
    console.log(`[cyberboss] syncBuffer=${syncBuffer ? "ready" : "empty"}`);
    console.log(
      `[cyberboss] durableInbox=${this.durableInboxCoordinator ? "enabled" : "staging_baseline"}`,
    );
    console.log(
      `[cyberboss] jobScheduler=${this.jobScheduler ? "enabled" : "staging_manual"}`,
    );
    console.log(
      `[cyberboss] durableOutbox=${this.outboxWorker ? "enabled" : "staging_direct"}`,
    );
    console.log(
      `[cyberboss] canonicalSync=${this.canonicalSyncCoordinator ? "spooling" : "staging_disabled"}`,
    );
    console.log(`[cyberboss] runtimeEndpoint=${runtimeState.endpoint || runtimeState.command || "(spawn)"}`);
    console.log(`[cyberboss] runtimeModels=${runtimeState.models?.length || 0}`);
    if (this.config.startWithLocationServer) {
      await this.ensureLocationServerStarted();
    }
    // 先把会话上下文补回来，再启动主动轮询——顺序反了的话，重启后的第一次
    // 主动打招呼会因为找不到投递目标而白跑一次模型。
    this.backfillContextTokensFromInbox();
    console.log("[cyberboss] bridge loop started; waiting for WeChat messages.");
    // 主动打招呼。轮询器常驻，开不开由主人在后台那一格决定——每一轮现读一次，
    // 所以关掉之后下一轮就停，打开也不用重启。
    //
    // startWithCheckin 保留：本地 `cyberboss start --checkin` 那条老路不变。
    // 云上没有那个参数，靠的是面板里的开关。
    if (this.config.startWithCheckin || this.personaStore) {
      console.log(
        `[cyberboss] checkin: 轮询器已启动（当前${
          this.personaStore?.read().proactive.enabled ? "开着" : "关着，可在后台打开"
        }）`,
      );
      void runSystemCheckinPoller(this.config, {
        readProactive: () => (this.personaStore
          ? this.personaStore.read().proactive
          : { enabled: this.config.startWithCheckin === true, minMinutes: 45, maxMinutes: 240, quietStart: 23, quietEnd: 8 }),
        // 主人是谁以 users 表的 role 为准。发错人就是一次非主人的模型调用。
        resolveOwnerSenderId: () => this.resolveOwnerSenderIdForCheckin(),
        // 所有开了「主动找我」的人，每人一份自己的间隔和静默时段。
        listTargets: () => this.listCheckinTargets(),
      }).catch((error) => {
        console.error(`[cyberboss] checkin poller stopped: ${error.message}`);
      });
    }

    const shutdown = createShutdownController(async () => {
      this.clearPendingImageInboundTimers();
      await this.closeLocationServer();
      await this.closePortalServer();
      this.jobScheduler?.stop();
      await this.runtimeAdapter.close();
      this.closeDurableInbox();
    });

    try {
      let consecutiveFailures = 0;
      while (!shutdown.stopped) {
        try {
          await Promise.all([
            this.flushDueReminders(),
            this.flushPendingInboundMessages(),
            this.flushPendingSystemMessages(),
            this.flushPendingTimelineScreenshots(),
            this.maybeRunHealthCheck(),
          ]);
          if (this.durableInboxCoordinator) {
            const results = await this.pollAccountsOnce({
              timeoutMs: this.resolveLongPollTimeoutMs(),
            });
            const verdict = this.classifyPollResults(results);
            for (const failure of verdict.failures) {
              this.noteAccountPollFailure(failure.accountId, failure.error);
            }
            for (const ok of verdict.successes) {
              this.accountPollFailureCounts.delete(ok.accountId);
              if (ok.durable.acceptedCount || ok.durable.rejectedCount) {
                console.log(
                  `[cyberboss] durable batch queued account=${ok.accountId} accepted=${ok.durable.acceptedCount} rejected=${ok.durable.rejectedCount}`,
                );
              }
            }
            if (verdict.ownerSessionExpired) {
              throw new Error("The WeChat session has expired. Run `npm run login` again.");
            }
            if (verdict.anyOk) {
              this.jobScheduler?.notePollSuccess();
              consecutiveFailures = 0;
            } else if (verdict.allFailedError) {
              // 这一轮落地的号全挂了，交给外层退避。
              throw verdict.allFailedError;
            }
            await this.outboxWorker?.runCycle();
            await this.canonicalSyncCoordinator?.runCycle();
            await this.jobScheduler?.runCycle();
          } else {
            const fetched = await this.channelAdapter.fetchUpdates({
              syncBuffer: this.channelAdapter.loadSyncBuffer(),
              timeoutMs: this.resolveLongPollTimeoutMs(),
            });
            assertWeixinUpdateResponse(fetched.response);
            this.channelAdapter.saveSyncBuffer(fetched.candidateCursor);
            this.channelAdapter.rememberBaselineStagingContextTokens(
              fetched.messages,
            );
            consecutiveFailures = 0;
            const messages = sortInboundUpdateMessages(fetched.messages);
            for (const message of messages) {
              if (shutdown.stopped) {
                break;
              }
              await this.handleIncomingMessage(message);
            }
          }
          await Promise.all([
            this.flushDueReminders(),
            this.flushPendingInboundMessages(),
            this.flushPendingSystemMessages(),
            this.flushPendingTimelineScreenshots(),
          ]);
        } catch (error) {
          if (shutdown.stopped) {
            break;
          }

          if (isSessionExpiredError(error)) {
            throw new Error("The WeChat session has expired. Run `npm run login` again.");
          }

          consecutiveFailures += 1;
          this.jobScheduler?.notePollFailure(error);
          console.error(`[cyberboss] poll failed: ${formatErrorMessage(error)}`);
          await sleep(consecutiveFailures >= MAX_CONSECUTIVE_FAILURES ? BACKOFF_DELAY_MS : RETRY_DELAY_MS);
        }
      }
    } finally {
      shutdown.dispose();
      this.clearPendingImageInboundTimers();
      await this.closeLocationServer();
      this.jobScheduler?.stop();
      await this.runtimeAdapter.close();
      this.closeDurableInbox();
    }
  }

  // 设置页面的 HTTP 服务。只监听 127.0.0.1：公网入口由 Cloudflare Tunnel
  // 提供，本机不开任何入站端口。没配域名就不启动，并说明原因。
  async startPortalServer() {
    if (!this.setupPortal || this.portalServer) {
      return null;
    }
    this.portalServer = new PortalHttpServer({
      portal: this.setupPortal,
      host: this.config.portalHost || "127.0.0.1",
      port: this.config.portalPort || 8787,
      usageProvider: () => this.remainingUsagePercent(),
      adminToken: this.config.adminToken || "",
      adminOverview: () => this.buildDashboardOverview(),
      adminInvite: () => this.issueDashboardInvite(),
      adminOwnerClaim: () => this.issueDashboardOwnerClaim(),
      adminOwnerBind: () => this.armDashboardOwnerBinding(),
      // 下面两个读写真实聊天内容与语气设置，一律要真令牌，不走首次免令牌。
      adminConversations: (query) => this.buildConversationFeed(query || {}),
      adminInsights: (query) => this.buildPersonInsights(query || {}),
      adminTrace: (query) => this.buildTurnTrace(query || {}),
      adminOps: () => this.buildOpsSnapshot(),
      adminPersonaRead: (query) => this.readDashboardPersona(query),
      adminPersonaWrite: (input) => this.writeDashboardPersona(input),
      publicEntry: () => this.buildPublicEntry(),
      publicEntryStatus: (ticket) => this.pollPublicEntryQr(ticket),
      adminSessionIssue: (input) => this.issueAdminSession(input),
      adminSessionVerify: (cookieHeader) => this.adminSessionValid(cookieHeader),
      personalSiteLogin: (token) => this.personalSiteLogin(token),
      personalSiteData: (cookieHeader) => this.personalSiteData(cookieHeader),
      personalSiteSettings: (cookieHeader, patch) => this.personalSiteSettings(cookieHeader, patch),
      adminSessionRevoke: (cookieHeader) => this.revokeAdminSession(cookieHeader),
      ownerActivationStart: () => this.startOwnerActivation(),
      ownerActivationPoll: (qrcode) => this.pollOwnerActivation(qrcode),
      // 还没有主人时，这套系统里不存在任何用户数据，后台也就没有什么可保护
      // 的；首次绑定因此不要令牌。绑上的那一刻起，后台恢复要令牌。
      firstRunProvider: () => this.userAdmission
        ? !this.userAdmission.ownerChannelBound()
        : false,
    });
    try {
      const address = await this.portalServer.start();
      console.log(
        `[cyberboss] 设置页面已启动 ${this.config.portalOrigin}/setup`
        + `（本机 ${address.host}:${address.port}，只接受来自隧道的请求）`,
      );
      return address;
    } catch (error) {
      this.portalServer = null;
      const code = normalizeErrorCode(error?.code) || "portal_server_failed";
      console.error(
        code === "EADDRINUSE"
          ? `[cyberboss] 设置页面启动失败：端口 ${this.config.portalPort || 8787} 被别的程序占用了。`
            + "换一个端口：在 .env 里加一行 CB_PORTAL_PORT=8788"
          : `[cyberboss] 设置页面启动失败 code=${code}`,
      );
      // 设置页面起不来不影响聊天，所以不中断启动——但状态里会如实显示。
      return null;
    }
  }

  // ── 体检 ──────────────────────────────────────────────────
  //
  // 「不依赖开发agent去运维」。今天那三个故障主人一个都发现不了：闸门卡住、
  // 同步 EACCES、接口 404——三个都不是资源问题，主机上那个自愈引擎查的是磁盘
  // 内存负载，对它们一无所知。这一层查的是结果：该发的发出去了吗、该同步的
  // 同步了吗、回话有多快、主动消息是不是在空转。

  // 十分钟一次。挂在主循环上而不是另开一个定时器：这样它和收发消息共用同一个
  // 进程状态，进程活着体检就活着，进程死了主人本来就会发现"它不回话了"。
  //
  // 启动后先等两分钟。刚起来的那一刻队列还没热，很多数字是假的低。
  async maybeRunHealthCheck() {
    const now = Date.now();
    if (!this.lastHealthCheckAt) {
      this.lastHealthCheckAt = now - HEALTH_CHECK_INTERVAL_MS + 120_000;
      return;
    }
    if (now - this.lastHealthCheckAt < HEALTH_CHECK_INTERVAL_MS) {
      return;
    }
    this.lastHealthCheckAt = now;
    await this.runHealthCheck().catch(() => {});
  }

  gatherHealthFacts() {
    const one = (sql, params = []) => {
      try {
        return this.runtimeSpoolDatabase.database.prepare(sql).all(...params);
      } catch {
        return [];
      }
    };
    const since = new Date(Date.now() - 86_400_000).toISOString();
    const outbox = one(
      "SELECT status AS k, COUNT(*) AS c FROM outbox_messages WHERE created_at>=? GROUP BY status",
      [since],
    );
    const bucket = (name) => Number(outbox.find((row) => row.k === name)?.c || 0);
    return {
      canonicalSyncedAt: one(
        "SELECT MAX(synced_at) AS v FROM sync_spool WHERE synced_at IS NOT NULL",
      )[0]?.v || "",
      backupAt: this.readLatestBackupAt(),
      // 入队到开始处理。今天那次是 190 秒，而正常是零点几秒。
      recentJobs: one(
        "SELECT queued_at AS queuedAt, started_at AS startedAt FROM jobs"
        + " WHERE started_at IS NOT NULL ORDER BY queued_at DESC LIMIT 20",
      ),
      runningJobs: one(
        "SELECT started_at AS startedAt FROM jobs WHERE status='running'",
      ),
      outbox: {
        confirmed: bucket("confirmed"),
        failed: bucket("failed") + bucket("dead"),
      },
      checkinSilentStreak: Number(this.checkinSilentStreak) || 0,
      schema: Number(one("SELECT MAX(version) AS v FROM schema_migrations")[0]?.v || 0),
      // 代码里注册了到第几版，库里就该是第几版。对不上＝迁移没跑上去，
      // 而那种坏是「页面打得开、聊天也通，只有新功能永远是空的」。
      schemaExpected: MIGRATIONS.length
        ? Math.max(...MIGRATIONS.map((migration) => migration.version))
        : 0,
    };
  }

  // 冷备是另一个服务写的，本进程读不到它的日志；快照目录的最新一个就是证据。
  readLatestBackupAt() {
    try {
      const root = this.config.backupLocalDir
        || path.join(this.config.stateDir || "", "snapshots");
      let newest = 0;
      for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
        if (!entry.isDirectory() || !entry.name.startsWith("backup_")) {
          continue;
        }
        const at = fs.statSync(path.join(root, entry.name)).mtimeMs;
        newest = Math.max(newest, at);
      }
      return newest ? new Date(newest).toISOString() : "";
    } catch {
      return "";
    }
  }

  // 每一轮体检。发现新问题就用微信告诉主人；好了也说一句。
  //
  // 零模型调用：这几句话是拼出来的，不是想出来的。体检本身不该花额度——否则
  // 「额度用完了」这个故障会导致「你收不到额度用完的通知」。
  async runHealthCheck() {
    if (!this.runtimeSpoolDatabase) {
      return null;
    }
    let report;
    try {
      report = evaluateHealth(this.gatherHealthFacts(), { now: Date.now() });
    } catch (error) {
      console.error(
        `[cyberboss] 体检本身出错了 code=${normalizeErrorCode(error?.code) || "health_check_failed"}`,
      );
      return null;
    }
    this.lastHealthReport = report;

    let previous = [];
    try {
      const stored = this.runtimeSpoolDatabase.getServiceState?.("health_reported");
      previous = Array.isArray(stored?.value?.ids) ? stored.value.ids : [];
    } catch {
      previous = [];
    }
    const diff = diffFindings(previous, report.findings);
    if (!diff.appeared.length && !diff.recovered.length) {
      return report;
    }
    try {
      // 只存固定的英文码。service_state 那一列是明文，人写的字一个都不能进。
      this.runtimeSpoolDatabase.setServiceState("health_reported", { ids: diff.active });
    } catch {
      // 存不下就退回"每轮都报"，吵，但不会漏。
    }

    for (const text of [buildAlertMessage(diff.appeared), buildRecoveryMessage(diff.recovered)]) {
      if (text) {
        await this.tellOwner(text);
      }
    }
    return report;
  }

  // 给主人发一条纯文本，不经过模型。
  //
  // 体检、告警这类话必须走这条路：它们要在**模型不可用的时候**也能送到，
  // 而那正是最需要通知他的时刻。
  async tellOwner(text) {
    const senderId = this.resolveOwnerSenderIdForCheckin();
    if (!senderId || !text) {
      return false;
    }
    try {
      const account = resolveAccountForUser(this.config, senderId);
      await this.channelAdapter.sendText({
        userId: senderId,
        text,
        accountId: account.accountId,
      });
      this.noteDirectReply(senderId, text, { delivered: true });
      return true;
    } catch (error) {
      console.error(
        `[cyberboss] 体检结果没发出去 code=${normalizeErrorCode(error?.code) || "tell_owner_failed"}`,
      );
      return false;
    }
  }

  // 后台那一页要的全部数据。都是计数和状态，不含任何用户标识。
  buildDashboardOverview() {
    const projection = this.projectOperationalStatus();
    const lines = (projection?.status?.business_lines || []).map((line) => ({
      label: PLAIN_LINE_NAMES[line.business_line] || line.business_line,
      state: line.state,
    }));
    let users = 0;
    let messagesToday = 0;
    if (this.runtimeSpoolDatabase) {
      try {
        users = Number(this.runtimeSpoolDatabase.database
          .prepare("SELECT COUNT(*) AS c FROM users WHERE status='active' AND role='user'")
          .get().c);
        const today = new Date().toISOString().slice(0, 10);
        for (const row of this.runtimeSpoolDatabase.database
          .prepare("SELECT metrics_json FROM activity_daily WHERE day=?").all(today)) {
          try {
            messagesToday += Number(JSON.parse(row.metrics_json).messages) || 0;
          } catch {
            // 单行读坏不影响其它行的计数。
          }
        }
      } catch {
        // 读不到就显示 0，不猜。
      }
    }
    // 前端靠这一位决定还要不要显示「绑主人」那一整块。
    let ownerBound = false;
    try {
      ownerBound = this.userAdmission ? this.userAdmission.ownerChannelBound() : false;
    } catch {
      // 读不出来就当没绑：多显示一个按钮，好过让人以为已经绑好了。
    }
    return Object.freeze({
      lines,
      users,
      messagesToday,
      ownerBound,
      uptimeSeconds: Math.floor(process.uptime()),
      log: this.recentLog(),
    });
  }

  // ── 运维一栏：这台机器现在到底是什么状态 ────────────────────
  //
  // 「全量的后台，能看到所有管理数据」。概览那一格只有四个数字，看不出机器
  // 在不在干活、卡在哪、还有多少额度。这里把它们一次给全。
  //
  // 只出计数、状态词和时间，**不含任何消息正文**——正文在对话栏，那一栏是
  // 另一条路。这一栏和对话栏一样挂在要令牌的路由上（OWNER_ONLY_ADMIN_APIS）。
  buildOpsSnapshot() {
    const numbers = (sql, params = []) => {
      try {
        return this.runtimeSpoolDatabase.database.prepare(sql).all(...params);
      } catch {
        return [];
      }
    };
    const counted = (rows) => rows.map((row) => ({
      label: String(row.k ?? ""),
      count: Number(row.c ?? 0),
    }));

    const projection = this.projectOperationalStatus();
    const snapshot = {
      ok: true,
      at: new Date().toISOString(),
      // 版本和跑了多久。部署完想确认"跑的是不是新的"，看这一格。
      release: {
        commit: normalizeText(this.config.canonicalDeployedCommit).slice(0, 12),
        uptimeSeconds: Math.floor(process.uptime()),
        node: process.version,
        runtime: this.runtimeAdapter?.describe?.().id || "",
        channel: this.channelAdapter?.describe?.().id || "",
      },
      // 现在管着几个微信号。多号之后这一格才有意义。
      accounts: this.liveAccountIds(),
      // 业务线状态（和概览同一份投影，这里给全，不只给名字）。
      lines: (projection?.status?.business_lines || []).map((line) => ({
        id: line.business_line,
        label: PLAIN_LINE_NAMES[line.business_line] || line.business_line,
        state: line.state,
        reason: line.reason || "",
      })),
      // 调度闸门：卡住的时候这里说得出为什么（负载、磁盘、队列积压）。
      // 这一格是真出过事的——磁盘被我自己的部署撑满、负载上 11，闸门锁死，
      // 一条回复都出不去，而当时后台上什么都看不出来。
      //
      // evaluated=false 的意思是「队列一直是空的，还没需要判过」。这和
      // 「判过了，结论是卡住」完全不是一回事：闸门只在队列里有活的时候才判
      // （见 job-scheduler 的 #dispatchNextRuntime），空队列时 lastGate 一直是
      // 构造时那个悲观初值。不分开的话，后台会指着一个根本不存在的故障。
      gate: (() => {
        const scheduler = this.jobScheduler;
        if (!scheduler) {
          return null;
        }
        const gate = scheduler.lastGate;
        return {
          evaluated: Boolean(scheduler.lastGateAt),
          at: scheduler.lastGateAt || "",
          state: gate?.state || "",
          reason: gate?.reason || "",
          action: gate?.action || "",
        };
      })(),
      queue: {
        jobs: counted(numbers("SELECT status AS k, COUNT(*) AS c FROM jobs GROUP BY status")),
        inbox: counted(numbers("SELECT status AS k, COUNT(*) AS c FROM inbox_messages GROUP BY status")),
        outbox: counted(numbers("SELECT status AS k, COUNT(*) AS c FROM outbox_messages GROUP BY status")),
      },
      users: counted(numbers("SELECT role || '/' || status AS k, COUNT(*) AS c FROM users GROUP BY role, status")),
      // 库的版本。想知道迁移有没有真的跑上去，看这一格。
      schema: Number(numbers("SELECT MAX(version) AS v FROM schema_migrations")[0]?.v || 0),
      // 还剩多少额度（百分比）。
      usagePercent: (() => {
        try {
          return Number(this.remainingUsagePercent()) || 0;
        } catch {
          return 0;
        }
      })(),
      // 别人能不能真的聊起来。
      //
      // 主人走的是 Codex，不用这张表；**别人走 provider router，必须有 key**。
      // 一把都没有的时候，每个访客不管说什么都只会拿到一句「去填密钥」，而后台
      // 上唯一的线索是「AI 连接 activation_pending」——没人看得懂那是什么意思。
      //
      // 两个来源，缺一不可地都要看：
      //   · 主人那把（systemd credential）——前 N 个人共用它，他们不用做任何事
      //   · 每个人自己填的（provider_credentials）——用完席位的人才要
      // 只数后者的话，主人那把明明接好了，面板还会报「一把都没有」。
      guestAi: (() => {
        let ownKeys = 0;
        try {
          ownKeys = Number(this.runtimeSpoolDatabase.database
            .prepare("SELECT COUNT(*) AS c FROM provider_credentials").get().c);
        } catch {
          ownKeys = 0;
        }
        const ownerKey = Boolean(this.ownerProviderCredential());
        const seats = this.resolveSeatLimit();
        if (ownerKey) {
          return {
            keys: ownKeys,
            ownerQuota: true,
            ready: true,
            note: `你的额度接好了。前 ${Number.isInteger(seats) ? seats : "几"} 个人直接用，什么都不用填；再往后的人要自己填一把。`,
          };
        }
        return {
          keys: ownKeys,
          ownerQuota: false,
          ready: ownKeys > 0,
          note: ownKeys > 0
            ? "你自己那把还没接上，所以只有自己填过密钥的人能聊。"
            : "你那把 AI 密钥服务还读不到，所以别人不管说什么都聊不起来。你自己不受影响（你走的是另一条）。",
        };
      })(),
      // 最近做过什么。和概览那一段同一份。
      log: this.recentLog(),
    };
    // 最近这些轮里，多少条压根没答上。这是"它有没有在好好工作"最直接的数。
    const recent = numbers(
      `SELECT status AS k, COUNT(*) AS c FROM jobs
       WHERE created_at >= ? GROUP BY status`,
      [new Date(Date.now() - 24 * 3_600_000).toISOString()],
    );
    snapshot.last24h = counted(recent);
    // 日记。这一栏挂在 ops 上，而 ops 在 OWNER_ONLY_ADMIN_APIS 名单里——永远
    // 要令牌，不走首次运行免令牌。日记是真实内容，和对话栏一个级别。
    snapshot.diary = this.listDiaryEntries();
    // 体检的最近一次结论。后台上要看得见「现在到底行不行」，而不是只有
    // 出问题时那条微信。
    snapshot.health = this.lastHealthReport
      ? Object.freeze({
        at: this.lastHealthReport.at,
        healthy: this.lastHealthReport.healthy,
        findings: this.lastHealthReport.findings.map((finding) => Object.freeze({
          title: finding.title,
          detail: finding.detail,
        })),
      })
      // 还没体检过和体检过没问题，是两件事。分不开的话，刚启动那几分钟会
      // 显示成"一切正常"，而那时候什么都还没测过。
      : Object.freeze({ at: "", healthy: null, findings: [] });
    return Object.freeze(snapshot);
  }

  // 后台页面上那段"最近发生了什么"。只留人话，且不含任何消息内容。
  recentLog() {
    return (this.dashboardLog || []).slice(-40);
  }

  noteForDashboard(text) {
    if (!this.dashboardLog) {
      this.dashboardLog = [];
    }
    // 主人的当地时间，不是 UTC。服务器跑在 UTC 上，直接 toISOString 会让面板上
    // 每一行都差八小时——主人看到「06:26」而他手机上是 14:26，两边对不上，
    // 于是这一栏的每一条都变得没法用来核对。
    this.dashboardLog.push(`${formatOwnerLocalTime(new Date())}  ${text}`);
    if (this.dashboardLog.length > 200) {
      this.dashboardLog = this.dashboardLog.slice(-200);
    }
  }

  // ── 后台登录 ───────────────────────────────────────────────
  //
  // 「我不可能每次都有 token」。所以令牌只用来换一次会话，之后靠 cookie；
  // cookie 掉了就在微信里发「后台」，机器人回一条一次性链接。长期令牌一次都
  // 不需要经过聊天记录，主人也一次都不需要记住它。
  //
  // 会话复用 web_sessions（和 /setup 同一张表），但**必须**校验它属于主人：
  // 普通用户在 /setup 拿到的也是这张表里的会话，不校验就等于把全部人的聊天
  // 记录开放给任何一个普通用户。

  // 下面三个不用 # 私有方法：本仓的测试大量借用 CyberbossApp.prototype 挂到
  // 一个精简接收者上跑（借用私有方法会直接抛 "Receiver must be an instance"）。
  // 那是这里唯一能"真的走生产实现"的测法，所以按约定保持可见，而不是靠语法
  // 隔离——真正的边界在 portal-server 的鉴权上。
  adminSessions() {
    if (!this.runtimeSpoolDatabase) {
      return null;
    }
    if (!this.adminSessionService) {
      this.adminSessionService = new SqliteSessionTokenService({
        database: this.runtimeSpoolDatabase.database,
        // 后台会话按天算，不是按分钟算——它要撑到主人下一次想看的时候。
        ttlMs: ADMIN_SESSION_TTL_MS,
      });
    }
    return this.adminSessionService;
  }

  adminTickets() {
    if (!this.runtimeSpoolDatabase) {
      return null;
    }
    if (!this.adminTicketService) {
      this.adminTicketService = new SqliteAdminLoginTickets({
        database: this.runtimeSpoolDatabase.database,
      });
    }
    return this.adminTicketService;
  }

  ownerUserId() {
    return this.runtimeSpoolDatabase ? this.runtimeSpoolDatabase.ownerUserId : "";
  }

  issueAdminSession({ ticket = "", renewFrom = "" } = {}) {
    const sessions = this.adminSessions();
    if (!sessions) {
      return Object.freeze({ ok: false, code: "SPOOL_DB_UNAVAILABLE" });
    }
    // 续期：已经是登录状态就换一张新的，旧的当场作废。页面每次打开都做一次，
    // 于是常用的设备永远不掉线，而 24 小时的上限对没人用的会话仍然成立。
    if (!ticket && renewFrom) {
      const previous = parseSessionCookie(renewFrom);
      if (previous) {
        try {
          sessions.revoke(previous);
        } catch {
          // 撤不掉旧的不影响发新的；旧的到点自己过期。
        }
      }
    }
    if (ticket) {
      // 一次性票：换不出来就是换不出来，不给第二次机会，也不说是哪一种失败。
      try {
        this.adminTickets().consume(ticket);
      } catch {
        return Object.freeze({ ok: false, code: "ADMIN_LINK_INVALID" });
      }
    }
    try {
      const issued = sessions.issue({ userId: this.ownerUserId() });
      this.noteForDashboard(ticket ? "用微信发来的链接登录了后台" : "登录了后台");
      return Object.freeze({
        ok: true,
        csrf: issued.csrf,
        expiresAt: issued.expiresAt,
        setCookie: issued.cookie,
      });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "ADMIN_SESSION_FAILED",
      });
    }
  }

  adminSessionValid(cookieHeader) {
    const sessions = this.adminSessions();
    if (!sessions) {
      return false;
    }
    const token = parseSessionCookie(cookieHeader);
    if (!token) {
      return false;
    }
    try {
      // requireCsrf:false —— 跨站写入由 SameSite=Strict 挡住，这里判的是"这个
      // 会话是不是主人的"。这一条不能省：/setup 的普通用户会话在同一张表里。
      const session = sessions.verify({ token, requireCsrf: false });
      return Boolean(session) && session.userId === this.ownerUserId();
    } catch {
      return false;
    }
  }

  revokeAdminSession(cookieHeader) {
    const sessions = this.adminSessions();
    const token = parseSessionCookie(cookieHeader);
    if (sessions && token) {
      try {
        sessions.revoke(token);
      } catch {
        // 撤不掉也要把 cookie 清掉：留一个页面上看不见、服务端还认的会话更糟。
      }
    }
    return sessions ? sessions.clearCookieHeader() : "";
  }

  // 微信里发「主页」走到这里。每个人拿到的是**自己那一页**。
  //
  // 票就是会话本身：web_sessions 那张表本来就是按 user_id 存的，签发给谁就只
  // 认到谁。不需要再造一套一次性票——而且这条路必须走 user_id，不能走 senderId：
  // 同一个人换个号 senderId 就变了，他的东西不该跟着丢。
  //
  // 安全边界靠 adminSessionValid 那一句 session.userId === ownerUserId()：普通
  // 人的会话和主人的会话在同一张表里，但后台那条路会把非主人的会话直接判假。
  issuePersonalSiteLink(userId) {
    const sessions = this.adminSessions();
    const origin = this.config.portalOrigin || "";
    const id = String(userId || "").trim();
    if (!sessions || !origin || !id) {
      return "";
    }
    try {
      const issued = sessions.issue({ userId: id });
      // 票放在 # 后面：片段不进请求行，隧道和服务器的访问日志都记不到它。
      return `${origin}/me#t=${issued.token}\n\n`
        + "点开就是你自己那一页，以后直接打开就行。";
    } catch {
      return "";
    }
  }

  // 把链接片段里的票换成 cookie。票本身就是会话，所以这里只验它是不是真的。
  personalSiteLogin(token) {
    const sessions = this.adminSessions();
    const value = String(token || "").trim();
    if (!sessions || !value) {
      return Object.freeze({ ok: false });
    }
    try {
      const session = sessions.verify({ token: value, requireCsrf: false });
      if (!session?.userId) {
        return Object.freeze({ ok: false });
      }
      return Object.freeze({ ok: true, cookie: sessions.cookieHeader(value) });
    } catch {
      return Object.freeze({ ok: false });
    }
  }

  // 身份只从 cookie 解。**没有任何入参能指定看谁的**——这样越权不是一个要防的
  // 攻击，而是一件写不出来的事。
  personalSiteData(cookieHeader) {
    const sessions = this.adminSessions();
    const token = parseSessionCookie(cookieHeader);
    if (!sessions || !token) {
      return Object.freeze({ ok: false });
    }
    try {
      const session = sessions.verify({ token, requireCsrf: false });
      if (!session?.userId) {
        return Object.freeze({ ok: false });
      }
      return this.buildPersonalSite(session.userId);
    } catch {
      return Object.freeze({ ok: false });
    }
  }

  // 「主页」这一页要的数据。**只给这一个人自己的东西**，一个字节别人的都不带。
  buildPersonalSite(userId) {
    const database = this.runtimeSpoolDatabase;
    const id = String(userId || "").trim();
    if (!database || !id) {
      return Object.freeze({ ok: false, code: "NOT_READY" });
    }
    const local = (value) => (value ? this.formatOwnerLocalTime(value) : "");
    const items = (kind) => database
      .listUserItems({ userId: id, kind, open: true, limit: 50 })
      .map((item) => Object.freeze({
        title: item.title,
        dueAt: local(item.dueAt),
        createdAt: local(item.createdAt),
        // media 的文件名、大小、是不是图片全在 note 里。漏掉它的话后台那一栏
        // 能显示出来，但每一条都缺元数据——看起来在工作，其实是空的。
        ...(kind === "media" ? { note: item.note } : {}),
      }));
    return Object.freeze({
      ok: true,
      todos: Object.freeze(items("todo")),
      events: Object.freeze(items("event")),
      // 他发过来的图片和文件。open:true 对 media 没有意义（媒体永远没有
      // done_at），所以它会全部列出来，这正是想要的。
      media: Object.freeze(items("media")),
      memories: Object.freeze(this.listMemoriesFor(id)),
      reminders: Object.freeze(this.listOwnReminders(id)),
      // 他自己的设置。页面上那个「主动找我」开关要显示当前状态，不能每次打开
      // 都是个不知道开没开的方块。
      settings: this.readPersonSettings(id),
    });
  }

  // 这个人自己的设置。现在只有「主动找我」，加别的项时往这里塞。
  readPersonSettings(userId) {
    const empty = Object.freeze({ proactive: null });
    const id = String(userId || "").trim();
    if (!id || !this.personaStore) {
      return empty;
    }
    try {
      return Object.freeze({ proactive: this.personaStore.readFor(id).proactive });
    } catch {
      return empty;
    }
  }

  // 「主页」上改自己的设置。和 personalSiteData 一样，**身份只从 cookie 解**，
  // 入参里没有任何能指定改谁的东西。
  personalSiteSettings(cookieHeader, patch = {}) {
    const sessions = this.adminSessions();
    const token = parseSessionCookie(cookieHeader);
    if (!sessions || !token || !this.personaStore) {
      return Object.freeze({ ok: false });
    }
    try {
      const session = sessions.verify({ token, requireCsrf: false });
      if (!session?.userId) {
        return Object.freeze({ ok: false });
      }
      // 只认 proactive 这一块。整份 persona 不从这里进——语气是主人定的默认，
      // 这一页改不了它。
      this.personaStore.setProactiveFor(session.userId, patch?.proactive || {});
      return Object.freeze({ ok: true, settings: this.readPersonSettings(session.userId) });
    } catch {
      return Object.freeze({ ok: false });
    }
  }

  // 日记。后台那一栏读的就是这些文件。
  //
  // 日记现在是**整机一份**（DiaryService 按日期写到 diaryDir），不按人分——
  // 写它的是主人那条 Codex 路径上的工具。所以它只出现在后台，不出现在别人的
  // 个人主页上：把主人的日记显示到访客那一页是串数据。
  //
  // 时间线目录现在是空的：timeline-service 在，但线上还没有任何一轮往里写过。
  // 所以后台不给它开一栏——开了就是一个永远为空的格子，看起来像坏了。
  listDiaryEntries({ limit = 14 } = {}) {
    const root = this.config.diaryDir;
    if (!root) {
      return [];
    }
    try {
      return fs.readdirSync(root)
        .filter((name) => /^\d{4}-\d{2}-\d{2}\.md$/.test(name))
        .sort()
        .reverse()
        .slice(0, Math.max(1, Math.min(60, Number(limit) || 14)))
        .map((name) => {
          const text = fs.readFileSync(path.join(root, name), "utf8");
          return Object.freeze({
            day: name.replace(/\.md$/, ""),
            // 后台那一栏只放摘要，点开才看全文——一屏塞不下一整天。
            text: text.length > 4000 ? `${text.slice(0, 4000)}\n……` : text,
          });
        });
    } catch {
      return [];
    }
  }

  // 谁要被主动找，每人一份自己的设置。
  //
  // 「每个用户的设置应该都是个人的，比如主动找我这个权限⋯应该是在用户下每个人
  // 都能单独保存。」没给自己设过的人沿用主人那一份当默认（和语气同一个规则）。
  //
  // 目标是 senderId（投递地址），设置按 user_id 存（隔离边界）。两者之间的换算
  // 走和别处同一条认人路径，不自己猜——猜错过一次，主动消息发给了刚扫码进来的
  // 陌生人，而主人一条都收不到。
  listCheckinTargets() {
    const targets = [];
    const seen = new Set();
    const add = (senderId, settings) => {
      const id = String(senderId || "").trim();
      if (!id || seen.has(id)) {
        return;
      }
      seen.add(id);
      targets.push({ senderId: id, settings });
    };

    // 主人。他那一份就是所有人的默认值。
    let ownerSettings = null;
    try {
      ownerSettings = this.personaStore?.read().proactive || null;
    } catch {
      ownerSettings = null;
    }
    add(this.resolveOwnerSenderIdForCheckin(), ownerSettings);

    // 其余每个说过话的人。
    if (!this.runtimeSpoolDatabase || !this.personaStore) {
      return targets;
    }
    try {
      for (const entry of this.runtimeSpoolDatabase.listRecentInboundForOwner({ limit: 500 })) {
        const senderId = String(entry?.payload?.senderId || "").trim();
        if (!senderId || seen.has(senderId)) {
          continue;
        }
        const userId = this.userAdmission?.users?.identify({
          channel: "weixin",
          botAccountRef: entry?.payload?.accountId || "",
          senderRef: senderId,
        })?.userId;
        if (!userId) {
          continue;
        }
        // readFor 没设过就回主人那一份，正是我们要的默认行为。
        add(senderId, this.personaStore.readFor(userId).proactive);
      }
    } catch {
      // 列不出来就只发主人的。宁可少发，也不能发错人。
    }
    return targets;
  }

  // 记着的关于这个人的事。
  //
  // profile_facts 那张表和 SqliteProfileStore 一直都在，但**从来没接进过 app**
  // ——存在的是一个谁都没调用过的模块。这里把读那一侧接上；写那一侧还没有，
  // 所以现在多数人这一栏是空的，那是真的空，不是坏了。
  // 库开了才有。构造那一刻还是 null，所以工具那边只能拿 getter 取。
  profileStoreOrNull() {
    if (!this.runtimeSpoolDatabase) {
      return null;
    }
    if (!this.profileStore) {
      this.profileStore = new SqliteProfileStore({
        database: this.runtimeSpoolDatabase.database,
      });
    }
    return this.profileStore;
  }

  listMemoriesFor(userId) {
    const store = this.profileStoreOrNull();
    if (!store) {
      return [];
    }
    try {
      const projection = store.projection(userId);
      return Object.entries(projection?.facts || {})
        .flatMap(([category, entries]) => Object.entries(entries || {})
          .map(([key, value]) => Object.freeze({
            category,
            key,
            text: typeof value === "string" ? value : JSON.stringify(value),
          })))
        .filter((fact) => fact.text && fact.text !== "null")
        .slice(0, 100);
    } catch {
      // 记忆读不出来不该让整页打不开。
      return [];
    }
  }

  // 这个人自己定的、还没到点的提醒。
  //
  // 提醒存在队列文件里而不是库里（它是一次性的），所以只能按发件人反推。用的是
  // 和主动打招呼同一条认人路径（userAdmission.users.identify），不是自己再猜一套
  // ——那条路已经因为猜错把别人的消息记到主人名下过一次。
  listOwnReminders(userId) {
    const identify = this.userAdmission?.users?.identify;
    if (typeof identify !== "function") {
      return [];
    }
    const reminders = [];
    for (const reminder of this.reminderQueue?.state?.reminders || []) {
      if (reminders.length >= 20) {
        break;
      }
      try {
        const identity = this.userAdmission.users.identify({
          channel: "weixin",
          botAccountRef: reminder.accountId,
          senderRef: reminder.senderId,
        });
        // 认不出来就跳过。宁可少显示，也不能把别人的提醒显示到他这一页上。
        if (identity?.userId !== userId) {
          continue;
        }
      } catch {
        continue;
      }
      reminders.push(Object.freeze({
        text: reminder.text,
        dueAt: this.formatOwnerLocalTime(new Date(reminder.dueAtMs).toISOString()),
      }));
    }
    return reminders;
  }

  // 微信里发「后台」走到这里。只有主人能拿到链接。
  issueAdminLoginLink() {
    const tickets = this.adminTickets();
    const origin = this.config.portalOrigin || "";
    if (!tickets || !origin) {
      return "";
    }
    try {
      const ticket = tickets.issue();
      const minutes = Math.max(1, Math.round(ticket.ttlMs / 60_000));
      // 票放在 # 后面：片段不进请求行，隧道和服务器的访问日志都记不到它。
      return `${origin}/admin#t=${ticket.token}\n\n`
        + `点开就进，${minutes} 分钟内有效，只能用一次。`
        + `进去之后这台手机就记住了，以后直接打开 ${origin} 就行。`;
    } catch {
      return "";
    }
  }

  // ── 谁能用：开放模式、席位、公开入口 ──────────────────────

  // 注册模式。面板上的设置优先于环境变量——主人改完不用重启，也不用碰服务器。
  resolveRegistrationMode() {
    try {
      const mode = this.personaStore?.read().access.mode;
      if (mode === "open" || mode === "invite") {
        return mode;
      }
    } catch {
      // 读不出来就退回配置里的那个。
    }
    return this.config.registrationMode || "invite";
  }

  resolveSeatLimit() {
    try {
      return this.personaStore.read().access.seats;
    } catch {
      // 读不出来返回 null＝不设限。席位判定坏掉不该把所有新用户挡在门外，
      // 那会让"开放模式"变成"谁都进不来"。
      return null;
    }
  }

  // 公开页要显示的东西。这一页**任何人都能打开**，所以它只含两样：一张现要的
  // 授权二维码，和一句怎么用。不含任何用量、人数、状态——那些都是运营信息，
  // 公开页上一个字都不该有。
  //
  // 「现要」是关键：一张码只对一个人有效，扫完就作废。主人配一张静态码给所有人
  // 扫是不行的——iLink 的授权码本来就是一次性的。
  async buildPublicEntry() {
    const bound = (() => {
      try {
        return this.userAdmission ? this.userAdmission.ownerChannelBound() : false;
      } catch {
        return false;
      }
    })();
    if (!bound) {
      // 主人自己都还没绑上，这时候放人进来只会绑出一堆没人管的号。
      return Object.freeze({
        ok: true, ready: false, status: "pending_activation",
        message: "这个机器人还没准备好，请稍后再来。",
      });
    }
    return this.mintPublicEntryQr();
  }

  // ── 公开入口：每个来的人现要一张自己的码 ────────────────────
  //
  // iLink 的授权码扫一次就生成一个**属于扫码那个人**的 bot 号
  // （ilink_bot_id + bot_token + ilink_user_id）。所以「每人扫码绑自己微信」
  // 不需要发明任何东西：让公开页现要一张授权码就是了。
  //
  // 这条路必须等多号轮询做完才能放出来（OPEN-2）。在那之前放码等于给人一个
  // 「能把你绑进来、然后系统当你不存在」的入口——扫进来的号根本没人轮询。
  //
  // 这一页没有鉴权，是刻意的；但每一次请求都会真的打一次 iLink，所以下面两条
  // 限流不是装饰：
  //   一、两次出码之间至少隔 PUBLIC_QR_MIN_INTERVAL_MS，同时在手的码不超过
  //       PUBLIC_QR_MAX_PENDING 张；
  //   二、只认自己发出去的票，且过期即弃——这样对外的长轮询次数被自己发出去的
  //       票数封死，别人没法拿一个编造的票号让我去打 iLink。
  async mintPublicEntryQr({ now = Date.now() } = {}) {
    const gate = this.publicEntryGate;
    this.prunePublicEntryTickets(now);
    if (now - gate.lastMintedAt < PUBLIC_QR_MIN_INTERVAL_MS) {
      return Object.freeze({ ok: true, ready: false, status: "busy", message: "现在人有点多，几秒后再刷新一下。" });
    }
    if (gate.tickets.size >= PUBLIC_QR_MAX_PENDING) {
      return Object.freeze({ ok: true, ready: false, status: "busy", message: "现在人有点多，过一会儿再来。" });
    }
    const { startWebLogin } = require("../adapters/channel/weixin/login");
    try {
      gate.lastMintedAt = now;
      const qr = await startWebLogin(this.config);
      const ticket = normalizeText(qr?.qrcode);
      const content = normalizeText(qr?.content);
      if (!ticket || !content) {
        return Object.freeze({ ok: true, ready: false, status: "unavailable", message: "现在拿不到二维码，过一会儿再试。" });
      }
      gate.tickets.set(ticket, now);
      return Object.freeze({
        ok: true,
        ready: true,
        status: "ready",
        ticket,
        // 服务端渲染成 SVG 再转 data URI：CSP 只放行 img-src 'self' data:，
        // 外部图床一律进不来。
        qrDataUri: svgDataUri(renderQrSvg(content, { ariaLabel: "加机器人的二维码" })),
        message: this.publicEntryQuotaNotice(),
      });
    } catch {
      // 公开页不吐内部错误码。
      return Object.freeze({ ok: true, ready: false, status: "unavailable", message: "现在拿不到二维码，过一会儿再试。" });
    }
  }

  async pollPublicEntryQr(ticket, { now = Date.now() } = {}) {
    const gate = this.publicEntryGate;
    this.prunePublicEntryTickets(now);
    const normalized = normalizeText(ticket);
    // 只认自己发出去的票。少了这一条，任何人都能拿编造的票号驱使我去打 iLink。
    if (!normalized || !gate.tickets.has(normalized)) {
      return Object.freeze({ ok: true, state: "expired", message: "这张码过期了，正在给你换一张。" });
    }
    const { pollWebLogin } = require("../adapters/channel/weixin/login");
    try {
      const result = await pollWebLogin(this.config, normalized);
      if (result.state === "confirmed") {
        gate.tickets.delete(normalized);
        this.noteForDashboard("有人扫码进来了");
        // 回给公开页的东西里**没有** accountId、没有 token、没有任何人的身份。
        return Object.freeze({
          ok: true,
          state: "confirmed",
          message: "好了。回到微信，跟它说句话就行。",
        });
      }
      if (result.state === "expired") {
        gate.tickets.delete(normalized);
        return Object.freeze({ ok: true, state: "expired", message: "这张码过期了，正在给你换一张。" });
      }
      return Object.freeze({
        ok: true,
        state: result.state === "scaned" ? "scaned" : "wait",
        message: result.state === "scaned" ? "扫到了，在微信里点一下确认。" : "",
      });
    } catch {
      return Object.freeze({ ok: true, state: "wait", message: "" });
    }
  }

  prunePublicEntryTickets(now = Date.now()) {
    for (const [ticket, mintedAt] of this.publicEntryGate.tickets) {
      if (now - mintedAt > PUBLIC_QR_TICKET_TTL_MS) {
        this.publicEntryGate.tickets.delete(ticket);
      }
    }
  }

  // 名额满了**不是拒绝**。前几个人用主人的额度，之后进来的人照样能用，只是
  // 要自己填一个 AI 密钥。所以这里说的是"要自己填密钥"，不是"你不能进"。
  publicEntryQuotaNotice() {
    try {
      const used = this.userAdmission?.users?.countActiveOrdinaryUsers?.();
      const limit = this.resolveSeatLimit();
      if (Number.isFinite(used) && Number.isInteger(limit) && used >= limit) {
        return "扫码加它，然后随便说句话。前面的免费名额满了，加上之后它会告诉你怎么填自己的 AI 密钥。";
      }
    } catch {
      // 读不出来就按"还有名额"说话：把能用的人挡在门外，比多说一句话糟糕得多。
    }
    return "用微信扫这个码加它，然后随便说句话就能用。";
  }

  // ── 语气面板 ───────────────────────────────────────────────

  // person 给了就读那个人自己的语气（没设过则显示主人那一行的值，并标出
  // inherited=true）；不给就是主人那一行本身。
  readDashboardPersona({ person = "" } = {}) {
    const senderId = normalizeText(person);
    const userId = senderId ? this.personaUserIdForSender(senderId) : "";
    const own = Boolean(userId) && Boolean(this.personaStore?.hasOwnPersona?.(userId));
    const persona = this.personaStore
      ? (userId ? this.personaStore.readFor(userId) : this.personaStore.read())
      : null;
    return Object.freeze({
      ok: true,
      persona: persona || {},
      // 这一份是谁的。空串＝主人那一行（所有人的默认值）。
      person: senderId,
      // 这个人是自己设过，还是在沿用主人那一行。后台要说得清楚，
      // 否则主人改完默认值会以为对每个人都生效了。
      inherited: Boolean(senderId) && !own,
      tones: TONE_PRESETS.map(({ id, label, hint }) => ({ id, label, hint })),
      lengths: LENGTH_PRESETS.map(({ id, label }) => ({ id, label })),
      maxNoteChars: MAX_NOTE_CHARS,
      proactiveLimits: { minMinutes: MIN_ALLOWED_MINUTES, maxMinutes: MAX_ALLOWED_MINUTES },
      maxSeats: MAX_SEATS,
      // 公开页地址，方便主人直接复制转发。
      joinUrl: this.config.portalOrigin ? `${this.config.portalOrigin}/join` : "",
      // 现在占了几个席位（后台里可以看，公开页上不给）。
      seatsUsed: (() => {
        try {
          return Number(this.userAdmission?.users?.countActiveOrdinaryUsers?.() || 0);
        } catch {
          return 0;
        }
      })(),
      // 主动打招呼要发给谁。空串表示还认不出主人，那时轮询器什么都不会做。
      proactiveTarget: this.resolveOwnerSenderIdForCheckin(),
      // 让主人看到真正发给模型的那段字。语气这种东西不给看就只能靠猜。
      preview: this.currentPersonaInstruction(userId),
    });
  }

  // 后台里人是按 senderId 认的（对话栏就是这么列的），语气按 user_id 存。
  // 这里做一次换算：先从最近的来信里找这个人属于哪个号，再算 user_id。
  personaUserIdForSender(senderId) {
    const sender = normalizeText(senderId);
    if (!sender || !this.runtimeSpoolDatabase) {
      return "";
    }
    try {
      for (const message of this.runtimeSpoolDatabase.listRecentInboundForOwner({ limit: 500 })) {
        if (message.payload?.senderId !== sender) {
          continue;
        }
        // 库里就存着这一行属于哪个 user_id，不用再推一遍。
        if (message.userId) {
          return message.userId;
        }
        return this.resolveUserIdForPersona({
          accountId: message.payload?.accountId || "",
          senderId: sender,
        });
      }
    } catch {
      // 查不到就当他还没说过话——那时候本来也没什么可设的。
    }
    return "";
  }

  writeDashboardPersona(input) {
    if (!this.personaStore) {
      return Object.freeze({ ok: false, code: "PERSONA_STORE_UNAVAILABLE" });
    }
    const person = normalizeText(input?.person);
    try {
      if (person) {
        const userId = this.personaUserIdForSender(person);
        if (!userId) {
          // 没说过话的人没有 user_id，也就没有可写的那一行。
          return Object.freeze({ ok: false, code: "PERSONA_USER_UNKNOWN" });
        }
        this.personaStore.writeFor(userId, input);
        this.noteForDashboard("改了对某个人的说话语气");
        return this.readDashboardPersona({ person });
      }
      this.personaStore.write(input);
      this.noteForDashboard("改了说话的语气");
      return this.readDashboardPersona();
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "PERSONA_WRITE_FAILED",
      });
    }
  }

  // ── 对话一栏：每个人发来的每一条，和机器人回的每一条 ─────────
  //
  // 这一栏是唯一会把真实聊天内容读出来的地方。它只挂在带真令牌的后台路由上
  // （见 portal-server 的 #handleOwnerOnlyApi），不写日志、不进证据、不进
  // canonical。去掉「收到，正在处理」之后，"我发的到底进去没有"这个问题就只
  // 能在这里回答，所以它必须把失败也照实显示出来，不能只显示成功的。

  // 机器人自己先开口的那些消息：主动打招呼、到点提醒、入门引导。
  //
  // 它们都不经过 outbox（outbox 的每一行都要挂在一个 job 上，而它们没有 job），
  // 发出去之后在库里一个字都不留。落进 bot_initiated_messages，后台「对话」栏
  // 才看得见它自己主动说过什么。
  //
  // 记账失败一律吞掉：宁可面板上少一条，也不能因为记账出错让主人收不到提醒。
  noteBotInitiated({ kind = "system", senderId = "", text = "", delivered = false, errorClass = "" } = {}) {
    if (!text || !this.runtimeSpoolDatabase) {
      return false;
    }
    const known = ["checkin", "reminder", "onboarding", "system"];
    // streamDelivery 传上来的是"这是一条系统回复"，分不出是哪一类；
    // dispatchSystemMessage 刚记下的那一位才知道。
    const resolved = known.includes(kind)
      ? kind
      : (this.activeSystemMessageKind || "system");
    try {
      this.runtimeSpoolDatabase.recordBotInitiatedMessage({
        kind: known.includes(resolved) ? resolved : "system",
        senderId,
        text,
        delivered,
        errorClass,
      });
      return true;
    } catch {
      return false;
    }
  }

  // 走 admission 直接回掉的那些（入门引导、状态、口令）也不经过 outbox。
  // 落库一份给「对话」栏；内存那份保留，作为数据库不可用时的降级显示。
  noteDirectReply(userId, text, { delivered = true, errorClass = "", kind = "onboarding" } = {}) {
    const persisted = this.noteBotInitiated({
      kind, senderId: userId, text, delivered, errorClass,
    });
    // 只有落库失败时才退回内存那一份。两份都留会让同一句话在面板上出现两次——
    // 一次挂在来信下面，一次作为独立卡片。
    return persisted ? true : this.noteDirectReplyInMemory(userId, text);
  }

  noteDirectReplyInMemory(userId, text) {
    if (!text) {
      return;
    }
    if (!this.directReplyLog) {
      this.directReplyLog = [];
    }
    this.directReplyLog.push({
      at: new Date().toISOString(),
      userId: String(userId || ""),
      text: String(text),
    });
    if (this.directReplyLog.length > 120) {
      this.directReplyLog = this.directReplyLog.slice(-120);
    }
  }

  // 参数：
  //   person   只看这一个发件人（微信 id）
  //   keyword  正文关键词，来信和回复都匹配——搜"闹钟"时不该因为这个词只出现在
  //            答复里就搜不到
  //   from/to  时间范围，YYYY-MM-DD 或完整 ISO
  //
  // 时间在 SQL 里筛，关键词只能解密之后在内存里筛（正文是密文）。所以带筛选时
  // 先取一个更大的窗口再过滤，窗口大小随 limit 放大但有硬上限——不能因为搜一个
  // 常见词就把整库解一遍。
  buildConversationFeed({ limit = 40, person = "", keyword = "", from = "", to = "" } = {}) {
    if (!this.runtimeSpoolDatabase) {
      return Object.freeze({ ok: false, code: "SPOOL_DB_UNAVAILABLE", threads: [], people: [] });
    }
    const wanted = Math.max(1, Math.min(200, Number(limit) || 40));
    const needle = String(keyword || "").trim().toLowerCase();
    const onlyPerson = String(person || "").trim();
    const filtering = Boolean(needle || onlyPerson);
    // 人员清单要覆盖到所有人，不能只看当前这一屏，否则筛完之后侧边就只剩一个人。
    const scanLimit = filtering ? Math.min(1200, Math.max(400, wanted * 10)) : Math.max(wanted, 120);

    let inbound = [];
    try {
      inbound = this.runtimeSpoolDatabase.listRecentInboundForOwner({
        limit: scanLimit,
        since: isoBound(from, "start"),
        until: isoBound(to, "end"),
      });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "CONVERSATION_READ_FAILED",
        threads: [],
        people: [],
      });
    }

    // 机器人自己先开口的那些（主动打招呼、到点提醒、入门引导）没有对应的来信，
    // 挂不到任何一条 thread 上，所以它们作为独立卡片并进同一条时间线。
    let initiated = [];
    try {
      initiated = this.runtimeSpoolDatabase.listBotInitiatedForOwner({
        limit: scanLimit,
        since: isoBound(from, "start"),
        until: isoBound(to, "end"),
      });
    } catch {
      // 读不到就只显示往来对话，不是致命的。
    }
    if (onlyPerson) {
      initiated = initiated.filter((entry) => entry.senderId === onlyPerson);
    }
    if (needle) {
      initiated = initiated.filter((entry) => String(entry.text || "").toLowerCase().includes(needle));
    }
    // 人员清单在过滤之前算：主人要能看见"还有谁"，而不是只看见筛剩下的那个。
    const peopleIndex = new Map();
    for (const message of inbound) {
      const sender = message.payload?.senderId || "";
      if (!sender) {
        continue;
      }
      const entry = peopleIndex.get(sender) || { id: sender, count: 0, lastAt: "", userId: message.userId };
      entry.count += 1;
      if (message.receivedAt > entry.lastAt) {
        entry.lastAt = message.receivedAt;
      }
      peopleIndex.set(sender, entry);
    }
    // 只被主动找过、自己一句话都没说过的人，也要出现在清单里。
    for (const entry of initiated) {
      if (entry.senderId && !peopleIndex.has(entry.senderId)) {
        peopleIndex.set(entry.senderId, {
          id: entry.senderId, count: 0, lastAt: entry.createdAt, userId: "",
        });
      }
    }
    // 「谁是主人」以 users 表的 role 为准——那是权威来源，不依赖环境变量。
    let roles = new Map();
    try {
      roles = this.runtimeSpoolDatabase.listUserRolesForOwner();
    } catch {
      // 读不到就都不打标签，比打错标签好。
    }
    const envOwners = new Set(this.knownOwnerSenders());
    const people = [...peopleIndex.values()]
      .sort((a, b) => (a.lastAt < b.lastAt ? 1 : -1))
      .map((entry, index) => {
        const isOwner = roles.get(entry.userId) === "owner" || envOwners.has(entry.id);
        return Object.freeze({
          id: entry.id,
          // 微信只给不透明 id，没有昵称。给一个稳定的短标签，主人至少分得清是几个人。
          label: isOwner ? "主人" : `用户 ${index + 1}`,
          short: entry.id.slice(0, 8),
          isOwner,
          count: entry.count,
          lastAt: entry.lastAt,
        });
      });

    let selected = onlyPerson
      ? inbound.filter((message) => (message.payload?.senderId || "") === onlyPerson)
      : inbound;

    // 关键词要连回复一起搜，所以先把这一批的回复取出来再筛。
    let outbound = [];
    let jobs = [];
    try {
      const correlationIds = selected.map((message) => message.correlationId);
      outbound = this.runtimeSpoolDatabase.listRecentOutboundForOwner({ correlationIds });
      jobs = this.runtimeSpoolDatabase.listRecentJobsForOwner({ correlationIds });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "CONVERSATION_READ_FAILED",
        threads: [],
        people,
      });
    }

    if (needle) {
      const replyTextByCorrelation = new Map();
      for (const item of outbound) {
        const previous = replyTextByCorrelation.get(item.correlationId) || "";
        replyTextByCorrelation.set(item.correlationId, `${previous}\n${item.text || ""}`);
      }
      selected = selected.filter((message) => {
        const asked = String(message.payload?.text || "").toLowerCase();
        const answered = String(replyTextByCorrelation.get(message.correlationId) || "").toLowerCase();
        return asked.includes(needle) || answered.includes(needle);
      });
    }

    const matched = selected.length + initiated.length;
    selected = selected.slice(0, wanted);
    inbound = selected;

    const repliesByCorrelation = new Map();
    for (const item of outbound) {
      const list = repliesByCorrelation.get(item.correlationId) || [];
      list.push(item);
      repliesByCorrelation.set(item.correlationId, list);
    }
    const jobByCorrelation = new Map(jobs.map((job) => [job.correlationId, job]));

    // 直接回复按发件人挂到"时间上紧挨着它之前"的那条来信上。inbound 是倒序的，
    // 所以对每条直接回复找第一条 receivedAt <= at 的同发件人来信。
    const directBySender = new Map();
    for (const entry of this.directReplyLog || []) {
      const list = directBySender.get(entry.userId) || [];
      list.push(entry);
      directBySender.set(entry.userId, list);
    }
    const claimedDirect = new Set();

    const threads = inbound.map((message) => {
      const sender = message.payload?.senderId || "";
      const replies = (repliesByCorrelation.get(message.correlationId) || [])
        .slice()
        .sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1))
        .map((item) => ({
          at: item.createdAt,
          kind: item.messageKind,
          text: item.payloadAvailable ? item.text : "",
          available: item.payloadAvailable,
          state: OUTBOX_STATE_LABELS[item.status] || item.status,
          rawStatus: item.status,
          delivered: item.status === "confirmed",
          error: item.lastErrorClass,
          attempts: item.attemptCount,
          source: "队列",
        }));

      for (const entry of directBySender.get(sender) || []) {
        if (claimedDirect.has(entry)) {
          continue;
        }
        if (entry.at >= message.receivedAt) {
          claimedDirect.add(entry);
          replies.push({
            at: entry.at,
            kind: "direct",
            text: entry.text,
            available: true,
            state: "已发出",
            rawStatus: "confirmed",
            delivered: true,
            error: "",
            attempts: 1,
            source: "直接回复（重启后不保留）",
          });
        }
      }
      replies.sort((a, b) => (a.at < b.at ? -1 : 1));

      const job = jobByCorrelation.get(message.correlationId) || null;
      return {
        at: message.receivedAt,
        // 发件人的微信 id。主人要分得清谁是谁，就只能给真的；这一栏本身要真令牌。
        who: sender,
        text: message.payloadAvailable
          ? String(message.payload?.text || "")
          : "",
        available: message.payloadAvailable,
        state: describeTurnState({ message, job, replies }),
        jobStatus: job ? job.status : "",
        jobError: job ? job.errorClass : "",
        // 拿这个去问 /admin/api/trace，就能看到这一轮它当时一步步在干什么。
        // 没有 job 的那些（被准入层直接回掉的）本来就没有执行轨迹。
        jobId: job ? job.jobId : "",
        rejectReason: message.rejectReason,
        replies,
      };
    });

    // 并进同一条时间线，从新到旧。主动那几条没有来信，只有它说的那一句。
    const BOT_KIND_LABELS = {
      checkin: "它主动想起你",
      reminder: "到点提醒",
      onboarding: "入门引导",
      system: "系统消息",
    };
    const initiatedCards = initiated.map((entry) => Object.freeze({
      at: entry.createdAt,
      who: entry.senderId,
      initiatedByBot: true,
      kindLabel: BOT_KIND_LABELS[entry.kind] || entry.kind,
      text: "",
      available: true,
      state: entry.delivered
        ? Object.freeze({ label: "它主动说的", tone: "ok", stuck: false })
        : Object.freeze({
          label: entry.errorClass ? `没发出去：${entry.errorClass}` : "没发出去",
          tone: "bad",
          stuck: true,
        }),
      jobStatus: "",
      jobError: "",
      rejectReason: "",
      replies: [Object.freeze({
        at: entry.createdAt,
        kind: entry.kind,
        text: entry.available ? entry.text : "",
        available: entry.available,
        state: entry.delivered ? "已发出" : "没发出去",
        rawStatus: entry.delivered ? "confirmed" : "failed_terminal",
        delivered: entry.delivered,
        error: entry.errorClass,
        attempts: 1,
        source: BOT_KIND_LABELS[entry.kind] || entry.kind,
      })],
    }));
    const merged = [...threads, ...initiatedCards]
      .sort((a, b) => (a.at < b.at ? 1 : -1))
      .slice(0, wanted);

    return Object.freeze({
      ok: true,
      threads: merged,
      people,
      // 数出来给主人一眼看的：这一屏里有几条根本没答上。
      unanswered: merged.filter((thread) => thread.state.stuck).length,
      // 命中多少条、显示了多少条、扫了多深。截断了就要说，不能让人以为"就这些"。
      matched,
      shown: merged.length,
      truncated: matched > merged.length,
      scanned: scanLimit,
      query: Object.freeze({ person: onlyPerson, keyword: String(keyword || "").trim(), from, to }),
    });
  }

  // 启动时把 context_token 缓存补回来。
  //
  // onAccepted 只在**新消息进来**时记。光有它的话，每次部署重启之后缓存又是空的，
  // 主动打招呼和到点的提醒都发不出去，直到有人先说一句话——而"主动"的意思恰恰是
  // 不等人先说话。所以启动时从已经收下的消息里把它们捞回来。
  //
  // 载荷是加密的，只有本进程解得开；补进去的是同一台机器上本来就有的东西，
  // 不产生任何新的暴露面。
  backfillContextTokensFromInbox({ limit = 200 } = {}) {
    if (!this.runtimeSpoolDatabase || typeof this.channelAdapter.rememberContextToken !== "function") {
      return 0;
    }
    const seen = new Set();
    let restored = 0;
    try {
      for (const message of this.runtimeSpoolDatabase.listRecentInboundForOwner({ limit })) {
        const senderId = message.payload?.senderId || "";
        // 载荷里刻意不存 contextToken（encryptedPayload 会删掉它），所以要去
        // inbox_messages 那一列单独解。
        if (!senderId || seen.has(senderId)) {
          continue;
        }
        seen.add(senderId);
        let token = "";
        try {
          const buffer = this.runtimeSpoolDatabase.readInboundContextToken(message.inboxId);
          token = buffer ? buffer.toString("utf8") : "";
        } catch {
          token = "";
        }
        // 载荷里带着这条消息**是从哪个号收到的**。必须一起传：不传就全落到
        // 主号名下，重启之后给别的号下面的人回信会拿主号的 token 去发，必被拒。
        const sourceAccountId = message.payload?.accountId || "";
        if (token && this.channelAdapter.rememberContextToken(senderId, token, sourceAccountId)) {
          restored += 1;
        }
      }
    } catch {
      // 补不回来不影响收发；最坏是主动消息要等这个人先说一句话。
    }
    if (restored) {
      console.log(`[cyberboss] 补回 ${restored} 个会话上下文（主动消息和提醒要用）`);
    }
    return restored;
  }

  // 主动打招呼该发给谁。
  //
  // 以 users 表的 role 为准，从最近一条属于主人的来信里取出他的微信号。取不到
  // 就返回空串——上层会退回旧的推断逻辑，再取不到轮询器直接不启动。这是刻意的：
  // 主动打招呼会真的唤醒模型，发错人就是一次非主人的模型调用，而 R19 冻结的
  // zero-agent 面明令禁止那件事。宁可不发。
  resolveOwnerSenderIdForCheckin() {
    if (!this.runtimeSpoolDatabase) {
      return "";
    }
    try {
      const ownerUserId = this.runtimeSpoolDatabase.ownerUserId;
      for (const message of this.runtimeSpoolDatabase.listRecentInboundForOwner({ limit: 200 })) {
        const sender = message.payload?.senderId || "";
        if (!sender) {
          continue;
        }
        // 从**发件人本身**推出他是谁，不看那一行存着的 user_id。
        //
        // 存着的那个曾经是错的：收信层一直没传 user_id，数据库默认记成主人，
        // 于是访客的消息也带着主人的 user_id。这个函数信了它，结果主动打招呼
        // 的目标变成了那位访客——朋友刚扫码进来，机器人就要开始主动找他，而
        // 主人自己一条都收不到。存的列会错，发件人推出来的不会。
        const derived = this.resolveUserIdForPersona({
          accountId: message.payload?.accountId || "",
          senderId: sender,
        });
        if (derived && derived === ownerUserId) {
          return sender;
        }
      }
    } catch {
      // 读不出来就当不知道，让上层决定。
    }
    return "";
  }

  // 这个人能不能用主人的额度。
  //
  // 规则：按开通先后，前 N 个（后台「最多让几个人用」那一格）用主人的密钥，
  // 第 N+1 个开始自己填。先来先得是唯一一个不用解释就说得通的规则。
  //
  // 任何一步不确定就返回 null＝不给——把主人的密钥错发给一个不该用的人，比让
  // 一个该用的人多填一次密钥严重得多。
  // 这个人还占不占得到席位（不管主人那把密钥现在有没有）。
  //
  // 和 resolveOwnerQuotaFor 分开：那个要密钥真的拿得到才返回，而这里只回答
  // 「按规矩他该不该用主人的额度」。密钥没接好时两者会不一致，而那种时候要说
  // 的话是「这边还没弄好」，不是「你去填密钥」——后者是把一件他做不了也不该
  // 做的事丢给他。
  ownerSeatAvailableFor(userId) {
    const limit = this.resolveSeatLimit();
    if (!Number.isInteger(limit) || limit <= 0) {
      return false;
    }
    try {
      const rank = Number(this.userAdmission?.users?.ordinaryUserRank?.(userId) || 0);
      return rank > 0 && rank <= limit;
    } catch {
      return false;
    }
  }

  resolveOwnerQuotaFor(userId) {
    const limit = this.resolveSeatLimit();
    if (!Number.isInteger(limit) || limit <= 0) {
      return null;
    }
    let rank = 0;
    try {
      rank = Number(this.userAdmission?.users?.ordinaryUserRank?.(userId) || 0);
    } catch {
      return null;
    }
    if (rank <= 0 || rank > limit) {
      return null;
    }
    return this.ownerProviderCredential();
  }

  // 主人自己那把 AI 密钥。只在内存里读一次就缓存，不落任何日志。
  //
  // 「有人反应说是 deepseek，这是不允许的，前面 5 个人都需要是 gpt 模型。」
  //
  // 以前这里把 deepseek 写死了：密钥名、providerId、model 三样全是常量。所以
  // 换模型必须改代码、重新部署——一个要卖出去的产品不该这样。
  //
  // 现在按**优先级找第一把能用的钥匙**：OpenAI 在前，DeepSeek 在后。配了
  // OpenAI 就走 OpenAI，前 N 个人自动跟着换，不用改一行代码。
  //
  // model 和 reasoning 也从配置来。这两样是外部服务认的**确切字符串**，
  // 猜错一个字母，每一轮都会失败——所以它们必须能填，不能由我编。
  ownerProviderCredential() {
    if (this.ownerCredentialCache !== undefined) {
      return this.ownerCredentialCache;
    }
    const candidates = [
      {
        providerId: "openai",
        envName: "OPENAI_API_KEY",
        credentialName: "openai-api-key",
        model: this.config.ownerModelOpenAI,
      },
      {
        providerId: "deepseek",
        envName: "DEEPSEEK_API_KEY",
        credentialName: "deepseek-api-key",
        model: this.config.ownerModelDeepSeek,
      },
    ];
    this.ownerCredentialCache = null;
    for (const candidate of candidates) {
      let apiKey = "";
      try {
        // 环境变量优先，其次 systemd credential。密钥只在内存里，不落日志、
        // 不落配置、不进任何一条聊天记录。
        apiKey = loadRuntimeTextSecret({
          envName: candidate.envName,
          credentialName: candidate.credentialName,
        });
      } catch {
        apiKey = "";
      }
      if (!apiKey) {
        continue;
      }
      this.ownerCredentialCache = Object.freeze({
        providerId: candidate.providerId,
        model: candidate.model,
        apiKey,
        // OpenAI 的推理档位（low / medium / high）。别的 provider 忽略它。
        reasoningEffort: candidate.providerId === "openai"
          ? this.config.ownerReasoningEffort
          : "",
      });
      console.log(
        `[cyberboss] 前 ${this.resolveOwnerSeatLimit()} 个人用主人这把钥匙：`
        + `${candidate.providerId} / ${candidate.model}`
        + (this.ownerCredentialCache.reasoningEffort
          ? ` / reasoning=${this.ownerCredentialCache.reasoningEffort}`
          : ""),
      );
      break;
    }
    return this.ownerCredentialCache;
  }

  // 把刚落盘的附件记进库，按人。
  //
  // 认不出这个人就整批不记：把照片记到错的人名下，比不记严重得多——那是隔离
  // 被破坏，而且从库里看不出来。
  //
  // 整个方法吞掉所有异常：收图这件事已经成功了（文件在磁盘上），记账失败不该
  // 让主人收到一条"图片接收失败"。
  recordIncomingMedia(saved, normalized) {
    if (!Array.isArray(saved) || !saved.length || !this.runtimeSpoolDatabase) {
      return 0;
    }
    const userId = String(this.activeUserContext?.userId || "").trim();
    if (!userId) {
      console.warn("[cyberboss] 附件没记进库：这一轮认不出是谁 count=" + saved.length);
      return 0;
    }
    let recorded = 0;
    for (const item of saved) {
      const title = String(item?.fileName || item?.name || "").trim();
      if (!title) {
        continue;
      }
      try {
        this.runtimeSpoolDatabase.createUserItem({
          userId,
          kind: "media",
          title: title.slice(0, 200),
          note: buildMediaNote(item),
          dueAt: null,
        });
        recorded += 1;
      } catch (error) {
        console.warn(
          `[cyberboss] 附件记账失败 code=${normalizeErrorCode(error?.code) || "media_record_failed"}`,
        );
      }
    }
    if (recorded) {
      console.log(
        `[cyberboss] 附件已记进库 count=${recorded} message=${String(normalized?.messageId || "").slice(0, 24)}`,
      );
    }
    return recorded;
  }

  resolveOwnerSeatLimit() {
    try {
      return Number(this.personaStore?.read().access.seats) || 5;
    } catch {
      return 5;
    }
  }

  // 记一步执行轨迹。
  //
  // 写失败一律吞掉：记不下轨迹绝不能让一轮回复挂掉。reply.delta 会非常密集
  // （模型每吐几个字就来一条），所以只记它的字数而不是逐条正文——正文在
  // reply.completed 那一条里已经有了，逐条存等于把同一段话存几十遍。
  noteTurnTrace(event) {
    if (!this.runtimeSpoolDatabase || !event || typeof event.type !== "string") {
      return;
    }
    const payload = event.payload || {};
    const turnId = String(payload.turnId || "");
    const threadId = String(payload.threadId || "");
    if (!turnId && !threadId) {
      return;
    }
    this.traceSeqByTurn = this.traceSeqByTurn || new Map();
    const key = turnId || threadId;
    const seq = (this.traceSeqByTurn.get(key) || 0) + 1;
    this.traceSeqByTurn.set(key, seq);
    if (this.traceSeqByTurn.size > 200) {
      // 只保最近的一批计数器，别让它无限长。
      this.traceSeqByTurn = new Map([...this.traceSeqByTurn].slice(-100));
    }

    let slim = null;
    if (event.type === "runtime.reply.delta") {
      slim = { chars: String(payload.text || "").length };
    } else if (event.type === "runtime.reply.completed") {
      slim = { text: String(payload.text || "").slice(0, 4000) };
    } else if (event.type === "runtime.context.updated") {
      slim = {
        inputTokens: payload.inputTokens ?? payload.input_tokens ?? null,
        outputTokens: payload.outputTokens ?? payload.output_tokens ?? null,
        totalTokens: payload.totalTokens ?? payload.total_tokens ?? null,
      };
    } else if (event.type === "runtime.turn.failed") {
      slim = { errorClass: String(payload.errorClass || ""), retryable: payload.retryable === true };
    } else if (event.type === "runtime.approval.requested") {
      slim = { command: String(payload.commandPreview || payload.command || "").slice(0, 400) };
    } else if (event.type === "runtime.turn.completed") {
      slim = { status: String(payload.status || ""), cancelled: payload.cancelled === true };
    }

    try {
      this.runtimeSpoolDatabase.recordTurnTrace({
        threadId, turnId, seq, kind: event.type, payload: slim,
      });
    } catch {
      // 见上。
    }
  }

  // 一轮回复的执行轨迹，给后台看。把 delta 折叠成一行"吐了 N 个字"，
  // 否则一屏全是几十条只差几个字的记录，反而看不出它干了什么。
  buildTurnTrace({ turnId = "", jobId = "", limit = 300 } = {}) {
    if (!this.runtimeSpoolDatabase) {
      return Object.freeze({ ok: false, code: "SPOOL_DB_UNAVAILABLE", steps: [] });
    }
    let rows = [];
    try {
      rows = this.runtimeSpoolDatabase.listTurnTracesForOwner({ turnId, jobId, limit });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "TRACE_READ_FAILED",
        steps: [],
      });
    }
    const ordered = rows.slice().sort((a, b) => (a.at === b.at ? a.seq - b.seq : (a.at < b.at ? -1 : 1)));
    const steps = [];
    for (const row of ordered) {
      if (row.kind === "runtime.reply.delta") {
        const previous = steps[steps.length - 1];
        if (previous && previous.kind === "runtime.reply.delta") {
          previous.chars += Number(row.payload?.chars || 0);
          previous.count += 1;
          previous.endedAt = row.at;
          continue;
        }
        steps.push({
          kind: row.kind, at: row.at, endedAt: row.at,
          chars: Number(row.payload?.chars || 0), count: 1, payload: null,
        });
        continue;
      }
      steps.push({ kind: row.kind, at: row.at, endedAt: row.at, payload: row.payload });
    }
    // 每一步离上一步多久——"慢在哪一步"是主人真正想知道的。
    let previousAt = steps.length ? steps[0].at : "";
    for (const step of steps) {
      const gap = new Date(step.at) - new Date(previousAt);
      step.gapMs = Number.isFinite(gap) && gap >= 0 ? gap : 0;
      previousAt = step.endedAt || step.at;
    }
    return Object.freeze({
      ok: true,
      turnId,
      jobId,
      steps: Object.freeze(steps.map((step) => Object.freeze(step))),
      totalMs: steps.length
        ? Math.max(0, new Date(steps[steps.length - 1].endedAt) - new Date(steps[0].at))
        : 0,
    });
  }

  // ── 一个人的画像 ────────────────────────────────────────────
  //
  // 后台「对话」那一栏原来是一屏平铺的卡片，谁跟谁说的、什么时候说的全糊在一起。
  // 主人真正想看的是"这个人跟它都聊了些什么"，所以这里按人算出一份画像：
  // 每天几条（贡献图）、什么时段活跃（热力图）、第一次和最近一次、答上没答上。
  //
  // 全部是计数，不含任何正文——正文在对话流里，那一份已经要真令牌了。
  buildPersonInsights({ person = "", days = 120 } = {}) {
    if (!this.runtimeSpoolDatabase) {
      return Object.freeze({ ok: false, code: "SPOOL_DB_UNAVAILABLE" });
    }
    const who = String(person || "").trim();
    const span = Math.max(7, Math.min(400, Number(days) || 120));
    // 从今天往前推 span 天。用 UTC 切天，和 received_at 的存储格式一致。
    const since = new Date(Date.now() - (span - 1) * 86_400_000)
      .toISOString().slice(0, 10);

    let inbound = [];
    let initiated = [];
    let outbound = [];
    let jobs = [];
    try {
      inbound = this.runtimeSpoolDatabase.listRecentInboundForOwner({
        limit: 2000, since: `${since}T00:00:00.000Z`,
      });
      initiated = this.runtimeSpoolDatabase.listBotInitiatedForOwner({
        limit: 2000, since: `${since}T00:00:00.000Z`,
      });
      const ids = inbound.map((m) => m.correlationId);
      outbound = this.runtimeSpoolDatabase.listRecentOutboundForOwner({ correlationIds: ids });
      jobs = this.runtimeSpoolDatabase.listRecentJobsForOwner({ correlationIds: ids });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "INSIGHTS_READ_FAILED",
      });
    }

    const mine = who
      ? inbound.filter((m) => (m.payload?.senderId || "") === who)
      : inbound;
    const myInitiated = who
      ? initiated.filter((entry) => entry.senderId === who)
      : initiated;

    // 按天计数：贡献图那一格一天。
    const byDay = new Map();
    // 星期几 × 小时：热力图。用本地时区（Asia/Shanghai）切，"几点活跃"要按人
    // 的作息看，不是按 UTC。
    const heat = Array.from({ length: 7 }, () => new Array(24).fill(0));
    const bump = (iso, weight) => {
      const at = new Date(iso);
      if (!Number.isFinite(at.getTime())) {
        return;
      }
      const local = new Date(at.getTime() + 8 * 3_600_000);
      const day = local.toISOString().slice(0, 10);
      byDay.set(day, (byDay.get(day) || 0) + weight);
      heat[local.getUTCDay()][local.getUTCHours()] += weight;
    };
    for (const message of mine) {
      bump(message.receivedAt, 1);
    }

    const jobByCorrelation = new Map(jobs.map((job) => [job.correlationId, job]));
    const repliedCorrelations = new Set(
      outbound.filter((item) => item.status === "confirmed").map((item) => item.correlationId),
    );
    let answered = 0;
    let stuck = 0;
    for (const message of mine) {
      if (repliedCorrelations.has(message.correlationId)) {
        answered += 1;
      } else if (jobByCorrelation.get(message.correlationId)?.status?.includes("fail")) {
        stuck += 1;
      }
    }

    const stamps = mine.map((m) => m.receivedAt).sort();
    // 连续说话的天数：从最近一天往回数，断一天就停。
    const dayKeys = [...byDay.keys()].sort().reverse();
    let streak = 0;
    if (dayKeys.length) {
      const cursor = new Date(`${dayKeys[0]}T00:00:00.000Z`);
      for (const key of dayKeys) {
        if (key === cursor.toISOString().slice(0, 10)) {
          streak += 1;
          cursor.setUTCDate(cursor.getUTCDate() - 1);
        } else {
          break;
        }
      }
    }

    return Object.freeze({
      ok: true,
      person: who,
      days: span,
      since,
      totals: Object.freeze({
        messages: mine.length,
        answered,
        stuck,
        botInitiated: myInitiated.length,
        activeDays: byDay.size,
        streak,
      }),
      firstAt: stamps[0] || "",
      lastAt: stamps[stamps.length - 1] || "",
      // 贡献图：连续 span 天，没说话的那天是 0，不跳过——跳过就看不出"断了几天"。
      daily: Object.freeze(Array.from({ length: span }, (_, index) => {
        const day = new Date(Date.now() - (span - 1 - index) * 86_400_000)
          .toISOString().slice(0, 10);
        return Object.freeze({ day, count: byDay.get(day) || 0 });
      })),
      heatmap: Object.freeze(heat.map((row) => Object.freeze([...row]))),
      // 「我需要能在 boss 页面看到全量信息数据记忆等」。
      //
      // 挂在这一栏而不是单开一个接口：主人在后台点开某个人，看到的应该是**这个
      // 人的全部**——说了多少话、什么时候活跃、记着他什么、他有哪些待办和日程，
      // 一屏之内。分成四个接口只会让"看一个人"变成点四次。
      ...this.buildPersonDetail(who),
    });
  }

  // 后台里点开一个人时，除了聊天统计还要看到的东西：记忆、待办、日程。
  //
  // 只在选了具体某个人时才查——「全部人」那个视图上列所有人的待办没有意义，
  // 而且会把一屏撑爆。
  buildPersonDetail(senderId) {
    const empty = {
      memories: [], todos: [], events: [], media: [], reminders: [], settings: { proactive: null },
    };
    const who = String(senderId || "").trim();
    if (!who || !this.runtimeSpoolDatabase) {
      return empty;
    }
    // 认人只走一条路：这条来信自己记着的 user_id。
    //
    // 原来这里是 identify({botAccountRef: resolveAccount(who)?.accountId ...})，
    // 而 **resolveAccount() 根本不收参数**——那个 who 被忽略，返回的永远是主号。
    // 于是不在主号下面的人全被按主号去认，认出来的是另一个 user_id（或者没有）。
    // 注释还写着"走和别处同一条认人路径"，其实不是：语气面板走的是
    // personaUserIdForSender（读来信上记着的 user_id）。
    //
    // 后果是同一个人在后台同一屏上出现两套设置：可编辑那块显示 120~360（他真的
    // 那一份），只读这块显示 45~240（认错身份之后的默认值）。记忆、待办、日程
    // 也一样按错的身份查——看起来是空的或者是别人的。
    //
    // 现在两块都用 personaUserIdForSender，同一个人只会有一个答案。
    let userId = "";
    try {
      userId = String(this.personaUserIdForSender(who) || "");
    } catch {
      return empty;
    }
    if (!userId) {
      return empty;
    }
    const local = (value) => (value ? this.formatOwnerLocalTime(value) : "");
    const items = (kind) => {
      try {
        return this.runtimeSpoolDatabase
          .listUserItems({ userId, kind, open: false, limit: 100 })
          .map((item) => Object.freeze({
            title: item.title,
            dueAt: local(item.dueAt),
            doneAt: local(item.doneAt),
            createdAt: local(item.createdAt),
            // 后台「他发来的图片和文件」那一栏读的就是这个。漏掉它的话那一栏
            // 会显示出来，但每条都缺大小和图标——看起来在工作，其实是空的。
            ...(kind === "media" ? { note: item.note } : {}),
          }));
      } catch {
        return [];
      }
    };
    return {
      memories: Object.freeze(this.listMemoriesFor(userId)),
      todos: Object.freeze(items("todo")),
      events: Object.freeze(items("event")),
      media: Object.freeze(items("media")),
      // 提醒和他自己的设置。主人要的是「在后台看到所有人的个人页面还有个人信息
      // 设置」——少这两样，后台看到的就不是他那一页，是他那一页的一部分。
      //
      // 这两个函数（这个和 buildPersonalSite）是同一份数据的两个出口，已经因为
      // 一边加了字段另一边没加而错过一次（media 的 note）。parity 有测试钉着，
      // 往任何一边加字段都要同时加到另一边。
      // 这两样取不到就给空的，别让整个「点开一个人」的接口 500。后台是排查工具，
      // 它自己挂掉的时候恰恰是最需要它的时候。
      reminders: Object.freeze(
        typeof this.listOwnReminders === "function" ? this.listOwnReminders(userId) : [],
      ),
      settings: typeof this.readPersonSettings === "function"
        ? this.readPersonSettings(userId)
        : { proactive: null },
    };
  }

  // 已知的主人发件号。只用来给对话栏打个「主人」标签，判权限不走这里。
  knownOwnerSenders() {
    const senders = new Set();
    for (const id of this.config.ownerSenderIds || this.config.allowedUserIds || []) {
      if (id) {
        senders.add(String(id));
      }
    }
    for (const id of this.rememberedOwnerSenders || []) {
      senders.add(String(id));
    }
    return [...senders];
  }

  issueDashboardInvite() {
    if (!this.userAdmission) {
      return Object.freeze({ ok: false, code: "ADMISSION_OFF" });
    }
    try {
      const invite = this.userAdmission.issueInvite({ maxUses: 1, ttlMs: 7 * 24 * 60 * 60 * 1000 });
      this.noteForDashboard("生成了一个邀请码");
      return Object.freeze({ ok: true, code: invite.code });
    } catch (error) {
      return Object.freeze({ ok: false, code: normalizeErrorCode(error?.code) || "INVITE_FAILED" });
    }
  }

  // 把「谁是主人」这件事和一个真实的微信号绑起来。
  //
  // 主人拿自己的微信当机器人号时，那个号的 id 永远不会作为发件人出现，所以他
  // 没有任何办法把自己绑上去——机器人会对包括他本人在内的每个人回一句"这个
  // 操作只有管理员可以使用"。后台令牌是服务器管理者才有的东西，用它换一个
  // 一次性认领码，再从任意一个微信号把码发过来，就把那个号绑成主人。
  issueDashboardOwnerClaim() {
    if (!this.userAdmission) {
      return Object.freeze({ ok: false, code: "ADMISSION_OFF" });
    }
    try {
      const claim = this.userAdmission.issueOwnerClaim();
      this.noteForDashboard("生成了一个主人认领码");
      return Object.freeze({ ok: true, code: claim.code, expiresAt: claim.expiresAt });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "OWNER_CLAIM_FAILED",
      });
    }
  }

  // R19 规定的 Owner 激活：在受保护的 /ops/wechat 扫 iLink 授权二维码。
  // 底下复用终端登录那套已验证的原语，登录逻辑一行没改。
  async startOwnerActivation() {
    const { startWebLogin } = require("../adapters/channel/weixin/login");
    try {
      const qr = await startWebLogin(this.config);
      // qrcode_img_content 是一段要被编码成二维码的链接，不是图片。终端流程用
      // qrcode-terminal 画它；网页这边在服务端渲染成 SVG 再转 data URI——CSP 只
      // 允许 img-src 'self' data:，外部图床一律进不来。
      const { renderQrSvg, svgDataUri } = require("../v8-prebuilt/public-entry/qr-svg");
      this.noteForDashboard("生成了 Owner 激活二维码");
      return Object.freeze({
        ok: true,
        qrcode: qr.qrcode,
        content: svgDataUri(renderQrSvg(qr.content)),
      });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "QR_FETCH_FAILED",
      });
    }
  }

  async pollOwnerActivation(qrcode) {
    const { pollWebLogin } = require("../adapters/channel/weixin/login");
    if (typeof qrcode !== "string" || !qrcode) {
      return Object.freeze({ ok: false, code: "QRCODE_REQUIRED" });
    }
    try {
      const result = await pollWebLogin(this.config, qrcode);
      if (result.state === "confirmed") {
        this.noteForDashboard("Owner 已完成微信授权");
      }
      return Object.freeze({ ok: true, ...result });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "POLL_FAILED",
      });
    }
  }

  // 开一扇 10 分钟的门：窗内第一个给机器人说话的人成为主人。比让人抄一串码
  // 好用——主人什么都不用复制，说句话就行。
  armDashboardOwnerBinding() {
    if (!this.userAdmission) {
      return Object.freeze({ ok: false, code: "ADMISSION_OFF" });
    }
    try {
      const armed = this.userAdmission.armOwnerBinding();
      this.noteForDashboard("打开了主人绑定窗口");
      return Object.freeze({ ok: true, expiresAt: armed.expiresAt, minutes: Math.round(armed.ttlMs / 60000) });
    } catch (error) {
      return Object.freeze({
        ok: false,
        code: normalizeErrorCode(error?.code) || "OWNER_BIND_FAILED",
      });
    }
  }

  async closePortalServer() {
    if (!this.portalServer) {
      return;
    }
    const server = this.portalServer;
    this.portalServer = null;
    await server.stop();
  }

  // 页面上那个进度条要的数字。读不到就按满额显示；真正的限额判定在每次模型
  // 调用之前由预算守卫做，不靠这个数。
  remainingUsagePercent() {
    if (!this.runtimeSpoolDatabase) {
      return 100;
    }
    try {
      const row = this.runtimeSpoolDatabase.database
        .prepare(
          `SELECT SUM(charged_tokens) AS charged
           FROM model_token_usage_daily
           WHERE day_utc = strftime('%Y-%m-%d','now')`,
        )
        .get();
      const charged = Number(row?.charged) || 0;
      const budget = Number(this.config.dailyTokenBudget) || 200_000;
      return Math.max(0, Math.min(100, Math.round(((budget - charged) / budget) * 100)));
    } catch {
      return 100;
    }
  }

  async ensureLocationServerStarted() {
    if (!this.projectServices?.whereabouts) {
      return null;
    }
    await this.projectServices.whereabouts.startServer({
      onAccepted: (result) => this.handleLocationAccepted(result),
    });
    console.log(
      `[cyberboss] locationServer=http://${this.config.locationHost}:${this.config.locationPort} store=${this.config.locationStoreFile}`
    );
    return this.projectServices.whereabouts.server || null;
  }

  async closeLocationServer() {
    if (!this.projectServices?.whereabouts) {
      return;
    }
    await this.projectServices.whereabouts.closeServer();
  }

  handleLocationAccepted(result) {
    if (!this.activeAccountId) {
      return;
    }

    const point = result?.appended?.point || null;
    const movementEvent = result?.appended?.movementEvent || null;
    const triggerText = buildLocationTriggerSystemText(point?.trigger);
    if (!triggerText && !movementEvent) {
      return;
    }

    const sessionStore = this.runtimeAdapter.getSessionStore();
    const senderId = resolvePreferredSenderId({
      config: this.config,
      accountId: this.activeAccountId,
      sessionStore,
    });
    const workspaceRoot = resolvePreferredWorkspaceRoot({
      config: this.config,
      accountId: this.activeAccountId,
      senderId,
      sessionStore,
    });
    if (!senderId || !workspaceRoot) {
      return;
    }

    if (triggerText && point?.id) {
      this.systemMessageQueue.enqueue({
        id: `location-trigger:${point.id}`,
        accountId: this.activeAccountId,
        senderId,
        workspaceRoot,
        text: triggerText,
        createdAt: normalizeIsoTime(point?.receivedAt) || normalizeIsoTime(point?.timestamp) || new Date().toISOString(),
      });
    }

    if (movementEvent) {
      this.systemMessageQueue.enqueue({
        id: `location-move:${movementEvent.id}`,
        accountId: this.activeAccountId,
        senderId,
        workspaceRoot,
        text: buildLocationMovementSystemText(movementEvent),
        createdAt: normalizeIsoTime(movementEvent?.movedAt) || new Date().toISOString(),
      });
    }
  }

  async sendTimelineScreenshot({
    senderId = "",
    outputFile = "",
    selector = "",
    range = "",
    date = "",
    week = "",
    month = "",
    category = "",
    subcategory = "",
    width = 0,
    height = 0,
    sidePadding = undefined,
    locale = "",
  } = {}) {
    return this.projectServices.timeline.queueScreenshot({
      userId: senderId,
      outputFile,
      selector,
      range,
      date,
      week,
      month,
      category,
      subcategory,
      width,
      height,
      sidePadding,
      locale,
    }, {});
  }

  async sendLocalFileToCurrentChat({ senderId = "", filePath = "" } = {}) {
    return this.projectServices.channelFile.sendToCurrentChat({
      userId: senderId,
      filePath,
    }, {});
  }

  async handleIncomingMessage(message) {
    const normalized = this.channelAdapter.normalizeIncomingMessage(message);
    if (!normalized) {
      return;
    }
    normalized.traceId = this.walkingSkeletonTrace?.beginInbound?.(normalized) || "";
    if (normalized.policyDecision?.accepted === false) {
      const code = normalized.policyDecision.code || "policy_rejected";
      console.warn(`[cyberboss] inbound rejected code=${code}`);
      if (code === "input_too_large") {
        await this.channelAdapter.sendText({
          userId: normalized.senderId,
          text: `⚠️ Input exceeds the ${normalized.policyDecision.maxInputBytes}-byte limit.`,
          contextToken: normalized.contextToken,
        }).catch(() => {});
      }
      return;
    }

    // v0.0.0.8 anchor. Every real inbound message is resolved to a server-owned
    // UserContext here, before any command is parsed, any workspace is bound
    // and any runtime is reached. A turn with no admission decision never
    // continues.
    const admission = await this.admitInboundMessage(normalized);
    if (!admission) {
      return;
    }

    this.primeDeferredRepliesForSender(normalized);
    await this.handlePreparedMessage(normalized, {
      allowCommands: true,
      userContext: admission.userContext,
      route: admission.route,
    });
  }

  // Returns the admission decision to continue with, or null when the turn was
  // fully answered here (onboarding, consent, suspension, or an ordinary-user
  // model turn). Returns an owner-shaped decision when multi-user admission is
  // off, which is the pre-existing single-user behaviour.
  // 在 durable inbox 建 job 之前跑的分流判定。返回 true 表示这一轮已经办完，
  // 不需要 runtime job，因此也不会发生任何模型调用。
  //
  // 只处理"不需要模型"的路由；主人与需要模型的普通用户 turn 一律返回 false，
  // 照常进入 job 队列。判不出来时同样返回 false——宁可多建一个 job，也不能因为
  // 准入层出问题就把用户的消息静默吞掉。
  admissionHandledBeforeJob(normalized) {
    if (!this.userAdmission) {
      return false;
    }
    let decision;
    try {
      decision = this.userAdmission.admit({
        botAccountRef: normalized.accountId,
        senderRef: normalized.senderId,
        text: normalized.text,
      });
    } catch (error) {
      console.warn(
        `[cyberboss] admission refused code=${normalizeErrorCode(error?.code) || "admission_failed"}`,
      );
      return false;
    }
    if (decision.route === "reply") {
      void this.sendAdmissionReply(normalized, decision.text);
      return true;
    }
    if (decision.route === "status") {
      void this.sendAdmissionReply(normalized, this.buildPlainLanguageStatus());
      return true;
    }
    if (decision.route === "admin_link") {
      void this.sendAdmissionReply(
        normalized,
        this.issueAdminLoginLink() || "后台还没配好域名，暂时给不了链接。",
      );
      return true;
    }
    if (decision.ownerClaimed) {
      this.rememberOwnerSender(normalized.senderId);
      this.noteForDashboard("有一个微信号绑成了主人");
      void this.sendAdmissionReply(normalized, OWNER_CLAIMED_NOTICE);
    }
    // 「X 分钟后提醒我 ⋯」在这里就办完。
    //
    // 主人说「我跟他说 1 分钟后提醒我，他没有回话，1 分钟后也没有提醒我」。
    // 查下来 reminder-queue.json 是空的：说明书里写着要主动建提醒、工具也挂着，
    // 但**模型没调就是没建**。这种话不能再交给模型的心情。
    //
    // 摆在准入之后：新人得先被认下来，不然一个陌生人第一句话就能往队列里塞东西。
    // 只对已经确立的人（主人和普通用户）生效，且这一轮不再唤醒模型。
    if (["owner", "user"].includes(decision.route) && !decision.ownerClaimed) {
      if (this.createDeterministicReminder(normalized)) {
        return true;
      }
      // 待办和日程同理。这里要 user_id：待办是**留着的东西**，必须按人隔离，
      // 不像提醒那样发完就没了。认不出这个人就不办，交回模型。
      const userId = String(decision.userContext?.userId || "").trim();
      if (userId && this.handleItemCommand(normalized, userId)) {
        return true;
      }
      if (this.handlePersonalSiteCommand(normalized, userId)) {
        return true;
      }
      if (this.handleHealthCommand(normalized)) {
        return true;
      }
    }
    // 普通用户在这里就办完，**不进 job 队列**。
    //
    // 这是「问它个问题，它回一句『这个操作只有管理员可以使用』」的原因。
    // job 队列的出口只有一个：dispatchPreparedTurn，而那条路是主人的 Codex，
    // 开头就有一道 owner-only 闸门。普通用户走到那里必然被这句话挡回来。
    //
    // 他们该走的是另一条（runUserModelTurn：预算、熔断、provider router）。
    // 那条路一直存在，但**只在非 durable 那条分支上被调用**——线上跑的是
    // durable，所以它一次都没被执行过。代码在不等于功能在，这个仓第七次栽在
    // 同一件事上。
    if (decision.route === "user" && decision.userContext) {
      // 席位内的前 N 个人改走 job 队列，也就是主人那条 Codex（gpt-5.6-terra）。
      // 那条路的出口 dispatchPreparedTurn 现在认席位内访客，并且强制访客档：
      // 只读沙箱、不给网络、审批 never，工具仍然被 tool-host 的 project.tool
      // 挡在外面。
      //
      // 席位外的人照旧走 runUserModelTurn（provider router + 预算 + 熔断）。
      if (hasOwnerSeat(this, decision.userContext.userId)) {
        return false;
      }
      void this.runUserModelTurn(normalized, decision.userContext)
        .catch((error) => {
          console.error(
            `[cyberboss] 普通用户这一轮失败 code=${normalizeErrorCode(error?.code) || "user_turn_failed"}`,
          );
        });
      return true;
    }
    // 只剩主人这一条要真正的 turn，交给 job 队列。
    return false;
  }

  // 同步准入，只回答一个问题：这一轮是不是主人的。
  //
  // 调度器要求 dispatchRuntime 返回真实的 threadId/turnId，所以非主人的分支
  // 不能在这里中断——那条路要在建 job 之前就分流，是另一件事。这里先把主人
  // 认得出来，因为在此之前主人连自己都绑不上。
  admitDurableTurn(normalized) {
    if (!this.userAdmission) {
      return null;
    }
    let decision;
    try {
      decision = this.userAdmission.admit({
        botAccountRef: normalized.accountId,
        senderRef: normalized.senderId,
        text: normalized.text,
      });
    } catch (error) {
      console.warn(
        `[cyberboss] admission refused code=${normalizeErrorCode(error?.code) || "admission_failed"}`,
      );
      return null;
    }
    // 访客的 UserContext 也要带出去，不能只认主人。
    //
    // 这里返回 null 的话，dispatchPreparedTurn 那边
    // `turnContext = prepared?.userContext || this.activeUserContext || null`
    // 拿到的是空的，第一个判断 `!turnContext` 直接成立，于是这个人收到一句
    // 「这个操作只有管理员可以使用」——他问什么都一样。
    //
    // 以前这样写没出事，是因为访客根本不会走到 job 队列（上面
    // admissionHandledBeforeJob 就把他们分流去 runUserModelTurn 了）。2026-07-30
    // 加「前 N 个席位走主人的 Codex」之后，席位内的访客**开始走这条路**，而这里
    // 还停在只认主人——于是前 5 个人一句话都发不出去。这是那次改动直接造成的。
    if (decision.route !== "owner" && decision.route !== "user") {
      return null;
    }
    if (decision.ownerClaimed) {
      this.rememberOwnerSender(normalized.senderId);
      this.noteForDashboard("有一个微信号绑成了主人");
      void this.sendAdmissionReply(normalized, OWNER_CLAIMED_NOTICE);
    }
    return decision.userContext || null;
  }

  async admitInboundMessage(normalized) {
    if (!this.userAdmission) {
      return Object.freeze({ route: "owner", userContext: null });
    }
    let decision;
    try {
      decision = this.userAdmission.admit({
        botAccountRef: normalized.accountId,
        senderRef: normalized.senderId,
        text: normalized.text,
      });
    } catch (error) {
      // Fail closed: an admission that cannot be decided is not a turn.
      console.warn(
        `[cyberboss] admission refused code=${normalizeErrorCode(error?.code) || "admission_failed"}`,
      );
      return null;
    }

    if (decision.route === "reply") {
      await this.sendAdmissionReply(normalized, decision.text);
      return null;
    }
    if (decision.route === "status") {
      await this.sendAdmissionReply(normalized, this.buildPlainLanguageStatus());
      return null;
    }
    if (decision.route === "admin_link") {
      await this.sendAdmissionReply(
        normalized,
        this.issueAdminLoginLink() || "后台还没配好域名，暂时给不了链接。",
      );
      return null;
    }
    if (decision.route === "user") {
      // 和 admissionHandledBeforeJob 里同一条规矩：席位内的人走主人的 Codex，
      // 所以这一轮不在这里办完，往下交给正常的 turn 流程。两处必须一致，否则
      // 同一个人在 durable 和非 durable 两条分支上会拿到不同的模型。
      if (!hasOwnerSeat(this, decision.userContext?.userId)) {
        await this.runUserModelTurn(normalized, decision.userContext);
        return null;
      }
    }
    if (decision.ownerClaimed) {
      // 第一条消息就把主人认下来了，告诉他这件事已经发生，并给出下一步。
      await this.sendAdmissionReply(normalized, OWNER_CLAIMED_NOTICE);
      this.rememberOwnerSender(normalized.senderId);
    }
    return decision;
  }

  // 微信里发「体检」当场查一次。
  //
  // 告警那条消息里写着「回一句『体检』」——那句话必须兑现。写了做不到的提示，
  // 比不写更糟：他照做之后发现没反应，下次连告警本身都不信了。
  //
  // 零模型调用：体检结果是拼出来的，不是想出来的。
  handleHealthCommand(normalized) {
    if (!HEALTH_KEYWORD.test(String(normalized.text || "").trim())) {
      return false;
    }
    let report = this.lastHealthReport;
    try {
      report = evaluateHealth(this.gatherHealthFacts(), { now: Date.now() });
      this.lastHealthReport = report;
    } catch {
      // 现查失败就用上一轮的结果，总比一句"查不了"强。
    }
    const text = report?.findings?.length
      ? buildAlertMessage(report.findings)
      : "都正常。回话、同步、备份、投递都是好的。";
    void this.sendAdmissionReply(normalized, text);
    return true;
  }

  // 模型调待办工具时，这一轮是谁。
  //
  // **只从发件人推**，不看模型传了什么。工具的 inputSchema 里根本没有 userId
  // 这个字段，就是为了让"给别人记一条"变成一件写不出来的事。
  resolveUserIdForToolCall(context) {
    const senderId = String(context?.senderId || "").trim();
    if (!senderId || !this.userAdmission?.users?.identify) {
      return "";
    }
    try {
      return String(this.userAdmission.users.identify({
        channel: "weixin",
        botAccountRef: String(context?.accountId || "").trim()
          || resolveAccountForUser(this.config, senderId).accountId,
        senderRef: senderId,
      })?.userId || "");
    } catch {
      return "";
    }
  }

  // 「记一下 买菜」「待办」「完成 1」→ 直接办，当场回。零模型、零 token。
  //
  // 返回 true 表示这一轮办完了。认不出来返回 false，照旧交给模型——它在聊天里
  // 顺手帮忙记东西那条路一直在，两者不冲突。
  handleItemCommand(normalized, userId) {
    const intent = parseItemIntent(normalized.text, {
      now: Date.now(),
      timeZone: OWNER_TIMEZONE,
    });
    if (!intent || !this.runtimeSpoolDatabase) {
      return false;
    }
    try {
      const reply = this.runItemAction(intent, userId);
      if (!reply) {
        return false;
      }
      void this.sendAdmissionReply(normalized, reply);
      return true;
    } catch (error) {
      console.error(
        `[cyberboss] 待办没办成 code=${normalizeErrorCode(error?.code) || "item_command_failed"}`,
      );
      return false;
    }
  }

  runItemAction(intent, userId) {
    const database = this.runtimeSpoolDatabase;
    if (intent.action === "add") {
      const item = database.createUserItem({
        userId,
        kind: intent.kind,
        title: intent.title,
        dueAt: intent.dueAtMs ? new Date(intent.dueAtMs).toISOString() : null,
      });
      this.noteForDashboard(intent.kind === "event" ? "记了一条日程" : "记了一条待办");
      return buildAddedMessage({ ...item, dueAtLabel: intent.dueAtLabel });
    }
    if (intent.action === "list") {
      return buildListMessage(
        intent.kind,
        database.listUserItems({ userId, kind: intent.kind, open: true }),
        { formatTime: (value) => this.formatOwnerLocalTime(value) },
      );
    }
    if (intent.action === "done") {
      const open = database.listUserItems({ userId, kind: "todo", open: true });
      // 只有一条的时候不用报序号——「完成」就是划掉那一条。
      const ordinal = intent.ordinal ?? (open.length === 1 ? 1 : null);
      if (!ordinal) {
        return buildDoneFailedMessage(open.length);
      }
      const done = database.completeUserItem({ userId, kind: "todo", ordinal });
      if (!done) {
        return buildDoneFailedMessage(open.length);
      }
      this.noteForDashboard("划掉了一条待办");
      return buildDoneMessage(done);
    }
    return "";
  }

  // 微信里发「主页」拿自己那一页的链接。
  //
  // 口令只留两个字，主人的原话是「减少关键词输入」。和「后台」同一层处理：
  // 一次性票，点开就进，之后这台手机记住。
  handlePersonalSiteCommand(normalized, userId) {
    if (!PERSONAL_SITE_KEYWORD.test(String(normalized.text || "").trim())) {
      return false;
    }
    void this.sendAdmissionReply(
      normalized,
      this.issuePersonalSiteLink(userId) || "主页还没配好域名，暂时给不了链接。",
    );
    return true;
  }

  // 「10 分钟后提醒我喝水」→ 建提醒 + 当场回一句确认。零模型、零 token。
  //
  // 返回 true 表示这一轮已经办完了，不用再往下走。认不出来就返回 false，一切
  // 照旧交给模型——宁可漏判，也不能把「我三点才下班」听成一个闹钟。
  createDeterministicReminder(normalized) {
    const intent = parseReminderIntent(normalized.text, {
      now: Date.now(),
      timeZone: OWNER_TIMEZONE,
    });
    if (!intent) {
      return false;
    }
    // 没有 context_token 就投不出去，这时候别答应。让模型接着聊，至少他知道
    // 有人在听——比"好，14:30 提醒你"然后什么都没发生强。
    const contextToken = String(normalized.contextToken || "").trim();
    if (!contextToken) {
      return false;
    }
    try {
      this.reminderQueue.enqueue({
        id: crypto.randomUUID(),
        accountId: normalized.accountId,
        senderId: normalized.senderId,
        contextToken,
        text: buildDueMessage(intent),
        dueAtMs: intent.dueAtMs,
        createdAt: new Date().toISOString(),
        direct: true,
      });
    } catch (error) {
      console.error(
        `[cyberboss] 提醒没建成 code=${normalizeErrorCode(error?.code) || "reminder_enqueue_failed"}`,
      );
      return false;
    }
    void this.sendAdmissionReply(normalized, buildConfirmation(intent));
    this.noteForDashboard("定了一个提醒");
    return true;
  }

  async sendAdmissionReply(normalized, text) {
    if (!text) {
      return;
    }
    // 先把这个人的 context_token 记下来。
    //
    // onAccepted 只对**收下**的消息触发，而走到这里的消息是被准入层直接办掉的
    // （handled_by_admission），它一次都不会触发。新人的第一句话正好走这条：
    // 于是他的 context_token 从来没被记过，之后任何一次主动消息、提醒、甚至
    // 这一条入门回复的重试，都找不到投递目标。
    try {
      this.channelAdapter.rememberContextToken?.(
        normalized.senderId,
        normalized.contextToken,
        normalized.accountId,
      );
    } catch {
      // 记不住不该挡下这条回复。
    }
    let delivered = true;
    let errorClass = "";
    try {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text,
        // 这条消息**是从哪个号收到的**，就用那个号回。
        //
        // 不传的话，适配器只能按 senderId 反查归属；而新人这一刻在任何一个号
        // 下面都还没有 context_token，反查必然落空，于是退回主号——拿主人的
        // bot token 去回一个挂在别人号下的人，微信必拒。
        // 这就是「新人加了但是没有回话」：码扫进来了，第一句话石沉大海。
        accountId: normalized.accountId,
        contextToken: normalized.contextToken,
      });
    } catch (error) {
      delivered = false;
      // normalizeErrorCode 是给数字 ret/errcode 用的，喂字符串会变成 null。
      // 这里要的正是字符串错误码（WEIXIN_CONTEXT_REQUIRED 之类），它是主人
      // 唯一能看懂"为什么没发出去"的线索。
      const code = String(error?.code || "");
      errorClass = /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(code) ? code : "send_failed";
      // 以前这里是 .catch(() => {})，发失败一声不吭，面板上还记成"已发出"。
      // 一条没送到的入门回复 = 这个人以为机器人是坏的。必须看得见。
      // 把微信真正回的那串也打出来。
      //
      // errorClass 只有 "WEIXIN_PROVIDER_ERROR" 这么一个笼统的分类，而
      // error.message 里是 `sendMessage ret=… errcode=… errmsg=…`——微信自己说的
      // 原因，而且 errmsg 已经过 redactSensitiveText。只打分类的后果是：出问题时
      // 只能靠猜（我就先后猜过"字数太长""token 过期"，两个都不对），真正的码就
      // 在手里却被丢掉了。
      console.error(
        `[cyberboss] 入门回复没发出去 account=${normalized.accountId} 原因=${errorClass}`
        + ` 详情=${String(error?.message || "").slice(0, 300)}`,
      );
    }
    // 这条不走 outbox，数据库里查不到，所以在这里留一份给后台「对话」栏——
    // 而且要照实记成功还是失败。
    // 主动问候要记成 checkin，不能跟入门引导混在一起。
    //
    // noteDirectReply 一直把 kind 写死成 "onboarding"（它原本只服务入门/口令的
    // 直回）。访客的主动问候也走这里，于是后台看到的是「入门引导 +1」，而
    // 「它主动找的」那一栏永远是 0——排查「他到底收到没有」时，这一列是唯一的
    // 依据，它指错了地方就等于没有依据。
    this.noteDirectReply(normalized.senderId, text, {
      delivered,
      errorClass,
      kind: normalized.provider === "system" ? "checkin" : "onboarding",
    });

    // 主动问候没送到就先存着，等他下次说话再补上。
    //
    // 微信这条通道上，"主动找一个很久没说话的人"是**做不到**的：能不能发出去
    // 取决于手里有没有一张还没用掉的 context_token，而这张票只在对方发消息时
    // 刷新。主人一直在跟它聊，所以他的票永远是新的；一个安静了一天的人，票早
    // 就用完了，怎么发都失败（WEIXIN_PROVIDER_ERROR）。
    //
    // 直接丢掉的话，这个人就永远等不到——主动找他这件事对他从来没发生过。
    // 存起来，他下次随便说一句，问候就先到。这是这条通道上能做到的最好结果。
    // 主人自己那条路早就这么干了（onDeferredSystemReply），访客这条路一直没接。
    if (!delivered && normalized.provider === "system") {
      try {
        this.deferSystemReply({
          userId: normalized.senderId,
          accountId: normalized.accountId,
          text,
          error: errorClass,
          kind: "checkin",
        });
        console.warn(
          `[cyberboss] 主动问候改成等他下次说话再补发 to=${String(normalized.senderId).slice(0, 10)}…`
          + ` 原因=${errorClass}`,
        );
      } catch {
        // 存不下就算了，不能反过来把这一轮搞挂。
      }
    }
  }

  // The ordinary-user lane. It never touches the Owner runtime adapter, the
  // workspace registry or the project tool host: those are Owner-only
  // capabilities, and this path holds a non-Owner UserContext.
  async runUserModelTurn(normalized, userContext) {
    // 先看是不是确定性口令：记一下 / 提醒我 / 我的记忆 / 最近7天 / 别再问我。
    // 是的话当场办掉，一次模型调用都不花——用户说"记一下"就必须真的记下来，
    // 而不是看模型这次会不会替他记。
    if (this.userCompanionTurn) {
      let handled = null;
      try {
        handled = this.userCompanionTurn.handle(userContext, normalized.text);
      } catch (error) {
        console.warn(
          `[cyberboss] companion turn failed code=${normalizeErrorCode(error?.code) || "companion_failed"}`,
        );
        handled = null;
      }
      if (handled) {
        await this.sendAdmissionReply(normalized, handled.text);
        return;
      }
      this.userCompanionTurn.recordMessage(userContext);
    }
    if (!this.userTurnRuntime) {
      await this.sendAdmissionReply(
        normalized,
        "服务还在启动中，请稍后再发一次。",
      );
      return;
    }
    await this.channelAdapter.sendTyping({
      userId: normalized.senderId,
      status: 1,
      contextToken: normalized.contextToken,
    }).catch(() => {});
    let result;
    try {
      result = await this.userTurnRuntime.handleTurn({
        userContext,
        text: normalized.text,
        // The channel message id is the idempotency key, so a redelivered
        // message is refused by the queue instead of charged twice.
        requestId: buildUserTurnRequestId(normalized),
      });
    } catch (error) {
      console.warn(
        `[cyberboss] user turn failed code=${normalizeErrorCode(error?.code) || "user_turn_failed"}`,
      );
      await this.sendAdmissionReply(normalized, "刚才没能处理成功，请再发一次。");
      return;
    } finally {
      await this.stopTypingForUser(normalized);
    }
    if (result.suppressReply) {
      return;
    }
    await this.sendAdmissionReply(normalized, result.text);
  }

  // 主人发「状态」时看到的东西：不是 JSON，是人话。数字全部来自同一份实测
  // 投影，没有另算一遍。
  buildPlainLanguageStatus() {
    const projection = this.projectOperationalStatus();
    if (!projection?.status) {
      return "现在读不到运行状况，稍后再发一次「状态」。";
    }
    const lines = projection.status.business_lines;
    const healthy = lines.filter((line) => line.state === "healthy").length;
    const pending = lines.filter((line) => line.state === "activation_pending");
    const blocked = lines.filter((line) => line.state === "blocked" || line.state === "degraded");
    const parts = [
      blocked.length ? "有地方出问题了 ⚠" : "运行正常 ✓",
      "",
      `功能模块：${healthy} 项正常，共 ${lines.length} 项`,
    ];
    if (blocked.length) {
      parts.push("", `需要处理：${blocked.map((line) => PLAIN_LINE_NAMES[line.business_line] || line.business_line).join("、")}`);
    }
    if (pending.length) {
      parts.push("", `还没配好（不影响聊天）：${pending.map((line) => PLAIN_LINE_NAMES[line.business_line] || line.business_line).join("、")}`);
    }
    if (projection.resource_gate && projection.resource_gate.admits_new_work === false) {
      parts.push("", `这台机器现在比较吃紧：${PLAIN_RESOURCE_REASONS[projection.resource_gate.reasonCode] || "资源不足"}`);
    }
    return parts.join("\n");
  }

  // 把认下来的主人写回 .env，这样重启之后不必再靠"第一条消息"来认。
  rememberOwnerSender(senderId) {
    const value = normalizeText(senderId);
    if (!value || !this.config.stateDir) {
      return;
    }
    try {
      updateEnvFile(path.join(this.config.stateDir, ".env"), {
        CB_OWNER_SENDER_IDS: value,
      });
    } catch {
      // 写不进去也不影响本次运行：主人身份已经在数据库里绑好了。
    }
  }

  async stopTypingForUser(normalized) {
    await this.channelAdapter.sendTyping({
      userId: normalized.senderId,
      status: 0,
      contextToken: normalized.contextToken,
    }).catch(() => {});
  }

  deferSystemReply({ threadId = "", userId = "", text = "", error = null, kind = "plain_reply", accountId = "" }) {
    return this.deferredSystemReplyQueue.enqueue({
      id: `${normalizeCommandArgument(threadId) || "system"}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
      // 这条是哪个号的就存哪个号。写死主号的话，取的那一侧
      // （drainForSender(normalized.accountId, senderId)）永远找不到它——
      // 和系统消息队列踩过的是同一个坑：多号加进来了，某一处还停在单号。
      accountId: normalizeText(accountId)
        || this.activeAccountId
        || this.channelAdapter.resolveAccount().accountId,
      senderId: userId,
      threadId,
      text,
      kind,
      createdAt: new Date().toISOString(),
      failedAt: new Date().toISOString(),
      lastError: error instanceof Error ? error.message : String(error || ""),
    });
  }

  primeDeferredRepliesForSender(normalized) {
    if (!normalized?.accountId || !normalized?.senderId || !normalized?.contextToken) {
      return;
    }
    const pendingReplies = this.deferredSystemReplyQueue.drainForSender(normalized.accountId, normalized.senderId);
    if (!pendingReplies.length) {
      return;
    }
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    this.streamDelivery.setDeferredReplyPrefix(bindingKey, formatDeferredSystemReplyBatch(pendingReplies));
    console.warn(
      `[cyberboss] queued deferred reply prefix sender=${normalized.senderId} count=${pendingReplies.length}`
    );
  }

  async handlePreparedMessage(normalized, { allowCommands, userContext = null }) {
    // The context travels with the message rather than being re-derived, so
    // every downstream step in this turn sees the same admission decision.
    this.activeUserContext = userContext || null;
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    this.streamDelivery.setReplyTarget(bindingKey, {
      userId: normalized.senderId,
      contextToken: normalized.contextToken,
      provider: normalized.provider,
      ...(normalized.traceId ? { traceId: normalized.traceId } : {}),
    });

    const command = parseChannelCommand(normalized.text);
    if (allowCommands && command) {
      await this.dispatchChannelCommand(normalized, command);
      return;
    }

    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const prepared = await this.prepareIncomingMessageForRuntime(normalized, workspaceRoot);
    if (!prepared) {
      return;
    }
    if (userContext) {
      prepared.userContext = userContext;
    }

    if (shouldBatchImageOnlyInbound(prepared)) {
      this.enqueuePendingImageInbound({ bindingKey, workspaceRoot, prepared });
      return;
    }

    if (this.hasPendingImageInbound(bindingKey, workspaceRoot) && isPlainTextPreparedMessage(prepared)) {
      const merged = await this.flushPendingImageInboundBatch({
        bindingKey,
        workspaceRoot,
        trailingPrepared: prepared,
      });
      if (merged) {
        return;
      }
    }

    if (this.hasPendingImageInbound(bindingKey, workspaceRoot)) {
      await this.flushPendingImageInboundBatch({ bindingKey, workspaceRoot });
    }

    await this.routePreparedInbound({ bindingKey, workspaceRoot, prepared });
  }

  async dispatchDurableRuntimeJob({ job, normalized, workspace }) {
    const runtimeId = this.runtimeAdapter.describe().id;
    const expectedRuntime = runtimeId === "claudecode" ? "claude" : runtimeId;
    if (job?.runtime !== expectedRuntime) {
      throw new Error("RUNTIME_ADAPTER_MISMATCH");
    }
    const resolvedWorkspace = this.workspaceRegistry.resolve(job.workspace_alias);
    if (
      resolvedWorkspace.alias !== workspace?.alias
      || resolvedWorkspace.root !== workspace?.root
    ) {
      throw new Error("WORKSPACE_BINDING_CHANGED");
    }
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    this.runtimeAdapter.getSessionStore().setActiveWorkspaceRoot(
      bindingKey,
      resolvedWorkspace.root,
    );
    this.streamDelivery.setReplyTarget(bindingKey, {
      userId: normalized.senderId,
      contextToken: normalized.contextToken,
      provider: normalized.provider,
      jobId: job.id,
      correlationId: job.correlation_id,
    });
    const prepared = await this.prepareIncomingMessageForRuntime(
      normalized,
      resolvedWorkspace.root,
    );
    if (!prepared) {
      throw new Error("DURABLE_RUNTIME_INPUT_REJECTED");
    }
    // 真正的准入锚点。
    //
    // admitInboundMessage 一直挂在 handleIncomingMessage 上，而线上根本不走那条
    // 路：消息是 durable inbox 收下、job scheduler 调度、最后到这里。于是主人
    // 认领码和绑定窗口都从来没有被执行过，每一条消息——包括主人自己发的——都以
    // 「这个操作只有管理员可以使用」结束。测试全绿，因为测试测的是那条没人走的路。
    const admitted = typeof this.admitDurableTurn === "function"
      ? this.admitDurableTurn(normalized)
      : null;
    const run = await this.dispatchPreparedTurn({
      bindingKey,
      workspaceRoot: resolvedWorkspace.root,
      prepared: admitted ? { ...prepared, userContext: admitted } : prepared,
      returnRun: true,
      deliveryContext: {
        jobId: job.id,
        correlationId: job.correlation_id,
      },
    });
    if (!run || typeof run !== "object") {
      throw new Error("DURABLE_RUNTIME_DISPATCH_FAILED");
    }
    return run;
  }

  async dispatchDurableControlJob({
    normalized,
    command,
    activeRun,
    workspace,
  }) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    this.streamDelivery.setReplyTarget(bindingKey, {
      userId: normalized.senderId,
      contextToken: normalized.contextToken,
      provider: normalized.provider,
    });
    if (
      activeRun
      && ["bind", "new"].includes(command.name)
    ) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `⚠️ /${command.name} is blocked while a Runtime job is active. Use /stop first.`,
        contextToken: normalized.contextToken,
      });
      return { resultCode: "active_runtime_guard" };
    }
    if (command.name === "stop") {
      if (!activeRun?.runBound || !activeRun.threadId || !activeRun.turnId) {
        await this.channelAdapter.sendText({
          userId: normalized.senderId,
          text: activeRun
            ? "⚠️ The active Runtime run is not safely bound; no cancellation was claimed."
            : "💡 There is no running Runtime job right now.",
          contextToken: normalized.contextToken,
        });
        return {
          resultCode: activeRun
            ? "active_run_unbound"
            : "no_active_runtime",
        };
      }
      await this.runtimeAdapter.cancelTurn({
        threadId: activeRun.threadId,
        turnId: activeRun.turnId,
        workspaceRoot: this.workspaceRegistry.resolve(
          activeRun.job.workspace_alias,
        ).root,
      });
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "⏹️ Stop request acknowledged by Runtime; final job state is pending the Runtime terminal event.",
        contextToken: normalized.contextToken,
      });
      return { resultCode: "cancel_acknowledged" };
    }
    await this.dispatchChannelCommand(normalized, command);
    return { resultCode: "command_processed" };
  }

  isTurnDispatchBlocked(bindingKey, workspaceRoot, { ignoreBoundary = false } = {}) {
    const scopeKey = buildScopeKey(bindingKey, workspaceRoot);
    if (!ignoreBoundary && scopeKey && this.turnBoundaryScopeKeys?.has(scopeKey)) {
      return true;
    }
    if (this.turnGateStore.isPending(bindingKey, workspaceRoot)) {
      return true;
    }
    const threadId = this.runtimeAdapter.getSessionStore().getThreadIdForWorkspace(bindingKey, workspaceRoot);
    const threadState = threadId ? this.threadStateStore.getThreadState(threadId) : null;
    return threadState?.status === "running" || hasRpcId(threadState?.pendingApproval?.requestId);
  }

  async dispatchPreparedTurn({
    bindingKey,
    workspaceRoot,
    prepared,
    returnRun = false,
    deliveryContext = null,
  }) {
    // AC-006 at the runtime boundary: `codex.turn` and `claudecode.turn` are
    // Owner-only. When admission is on, a turn that reaches the Owner runtime
    // without an Owner context is refused here rather than downgraded, so the
    // count of non-Owner runtime dispatches is structurally zero.
    const turnContext = prepared?.userContext || this.activeUserContext || null;
    // 「让前 5 个人也走我的 Codex」。席位内的访客放行，但**只放行到访客档**：
    // 只读沙箱、不给网络、审批策略 never。工具那道闸门不在这里，在 tool-host
    // 的 project.tool——访客的 UserContext 过不了它，所以他碰不到主人的日记、
    // 时间线、文件。这里放开的只是「能不能用这个模型说话」。
    const seatedGuest = Boolean(turnContext && !turnContext.isOwner)
      && hasOwnerSeat(this, turnContext.userId);
    if (this.userAdmission && prepared?.provider !== "system") {
      const capability = this.runtimeAdapter.describe().id === "claudecode"
        ? "claudecode.turn"
        : "codex.turn";
      if (!turnContext || (!turnContext.may(capability) && !seatedGuest)) {
        console.warn("[cyberboss] runtime dispatch refused code=owner_only_capability");
        await this.channelAdapter.sendText({
          userId: prepared.senderId,
          text: "这个操作只有管理员可以使用。",
          contextToken: prepared.contextToken,
        }).catch(() => {});
        return false;
      }
    }
    workspaceRoot = this.workspaceRegistry.assertAllowedRoot(workspaceRoot).root;
    const pendingScopeKey = this.turnGateStore.begin(bindingKey, workspaceRoot);
    await this.channelAdapter.sendTyping({
      userId: prepared.senderId,
      status: 1,
      contextToken: prepared.contextToken,
    }).catch(() => {});

    try {
      const model = this.runtimeAdapter.getSessionStore().getRuntimeParamsForWorkspace(bindingKey, workspaceRoot).model;
      const runtimeTurn = await this.buildRuntimeTurn({ prepared, model });
      const sendTurn = typeof this.runtimeAdapter.sendTurn === "function"
        ? this.runtimeAdapter.sendTurn.bind(this.runtimeAdapter)
        : this.runtimeAdapter.sendTextTurn.bind(this.runtimeAdapter);
      const turn = await sendTurn({
        bindingKey,
        workspaceRoot,
        text: runtimeTurn.text,
        attachments: runtimeTurn.attachments,
        model,
        // 席位内访客走访客档；主人和系统消息保持原样（空串＝原来的默认）。
        // 这个值必须真的传下去：适配器和 rpc-client 两层都是按名字解构的。
        accessMode: seatedGuest ? "guest-chat" : "",
        metadata: {
          workspaceId: prepared.workspaceId,
          accountId: prepared.accountId,
          senderId: prepared.senderId,
        },
      });
      this.walkingSkeletonTrace?.record?.({
        stage: "runtime_dispatched",
        traceId: prepared.traceId,
        threadId: turn.threadId,
        turnId: turn.turnId,
      });
      this.runtimeContextStore?.setActiveContext?.({
        workspaceRoot,
        runtimeId: this.runtimeAdapter.describe().id,
        threadId: turn.threadId,
        bindingKey,
        accountId: prepared.accountId,
        senderId: prepared.senderId,
        // Published so the project tool host can gate on the admitted role even
        // when a tool call arrives over MCP without a context of its own.
        userRole: turnContext ? turnContext.role : "",
        userStatus: turnContext ? turnContext.status : "",
        admissionEnforced: Boolean(this.userAdmission),
      });
      this.turnGateStore.attachThread(pendingScopeKey, turn.threadId);
      const replyTarget = {
        userId: prepared.senderId,
        contextToken: prepared.contextToken,
        provider: prepared.provider,
        ...(deliveryContext?.jobId
          ? {
              jobId: deliveryContext.jobId,
              correlationId: deliveryContext.correlationId || "",
            }
          : {}),
        ...(prepared.traceId ? { traceId: prepared.traceId } : {}),
      };
      if (turn.turnId) {
        this.streamDelivery.bindReplyTargetForTurn({
          threadId: turn.threadId,
          turnId: turn.turnId,
          target: replyTarget,
        });
      } else {
        this.streamDelivery.queueReplyTargetForThread(turn.threadId, replyTarget);
      }
      return returnRun
        ? Object.freeze({ threadId: turn.threadId, turnId: turn.turnId })
        : true;
    } catch (error) {
      this.turnGateStore.releaseScope(bindingKey, workspaceRoot);
      if (deliveryContext?.jobId) {
        throw error;
      }
      const messageText = error instanceof Error ? error.message : String(error || "unknown error");
      await this.channelAdapter.sendText({
        userId: prepared.senderId,
        text: `❌ Request failed\n${messageText}`,
        contextToken: prepared.contextToken,
      }).catch(() => {});
      return false;
    }
  }

  async buildRuntimeTurn({ prepared, model = "" }) {
    if (prepared?.provider === "system") {
      return {
        text: String(prepared.text || "").trim(),
        attachments: [],
      };
    }
    const visionContext = await resolveVisionContext({
      prepared,
      config: this.config,
      runtimeAdapter: this.runtimeAdapter,
      model,
    });
    return {
      text: assembleRuntimeTurnText({
        prepared,
        config: this.config,
        visionContext,
        // 每一轮现读一次，不缓存：在后台改完语气，下一句话就该变。
        // 按人读：每个人可以有自己的语气，没设过的沿用主人那一行。
        personaInstruction: this.currentPersonaInstruction(
          this.resolveUserIdForPersona(prepared),
        ),
      }),
      attachments: Array.isArray(visionContext.runtimeAttachments) ? visionContext.runtimeAttachments : [],
      visionContext,
    };
  }

  // 语气块。读不出来就返回空串——语气不是必需品，不能因为它发不出消息。
  //
  // 给了 userId 就读那个人自己的（没设过则沿用主人那一行）。不给就是主人的
  // 默认值——后台预览走这条。
  currentPersonaInstruction(userId = "") {
    if (!this.personaStore) {
      return "";
    }
    try {
      const persona = userId
        ? this.personaStore.readFor(userId)
        : this.personaStore.read();
      return renderPersonaInstruction(persona);
    } catch {
      return "";
    }
  }

  // 这条来信该记在谁名下。
  //
  // 返回 null 表示认不出来——那时退回主人名下（老行为）。**只返回 users 表里
  // 真的存在的那一个**：数据库对不认识的 user_id 会抛 USER_NOT_FOUND，那会让
  // 整批消息卡在游标之前反复重投，比记错域还糟。
  //
  // 调用点排在准入层之后，所以新人这时候已经被注册进 users 表了。
  scopeUserIdForInbound(normalized) {
    const userId = this.resolveUserIdForPersona(normalized);
    if (!userId || !this.runtimeSpoolDatabase) {
      return null;
    }
    try {
      const known = this.runtimeSpoolDatabase.database
        .prepare("SELECT 1 FROM users WHERE user_id=?")
        .get(userId);
      return known ? userId : null;
    } catch {
      return null;
    }
  }

  // prepared 里只有 accountId + senderId；语气按 user_id 存，和记忆同一个
  // 隔离边界。这里把前者换算成后者，换不出来就返回空串，上层退回主人那一行。
  resolveUserIdForPersona(prepared) {
    const botAccountRef = normalizeText(prepared?.accountId);
    const senderRef = normalizeText(prepared?.senderId);
    if (!botAccountRef || !senderRef || !this.userAdmission?.users?.identify) {
      return "";
    }
    try {
      const identity = this.userAdmission.users.identify({
        channel: "weixin",
        botAccountRef,
        senderRef,
      });
      return normalizeText(identity?.userId);
    } catch {
      return "";
    }
  }

  async routePreparedInbound({ bindingKey, workspaceRoot, prepared }) {
    if (this.isTurnDispatchBlocked(bindingKey, workspaceRoot)) {
      this.bufferPendingInboundMessage({ bindingKey, workspaceRoot, prepared });
      return false;
    }
    return this.dispatchPreparedTurn({ bindingKey, workspaceRoot, prepared });
  }

  hasPendingImageInbound(bindingKey, workspaceRoot) {
    return this.pendingImageInboundByScope.has(buildScopeKey(bindingKey, workspaceRoot));
  }

  enqueuePendingImageInbound({ bindingKey, workspaceRoot, prepared }) {
    const scopeKey = buildScopeKey(bindingKey, workspaceRoot);
    if (!scopeKey || !prepared) {
      return;
    }

    const current = this.pendingImageInboundByScope.get(scopeKey) || {
      bindingKey,
      workspaceRoot,
      messages: [],
      timer: null,
    };
    current.messages.push(clonePreparedInboundMessage(prepared));
    this.pendingImageInboundByScope.set(scopeKey, current);
    this.schedulePendingImageInboundFlush(scopeKey, bindingKey, workspaceRoot);
    void this.channelAdapter.sendTyping({
      userId: prepared.senderId,
      status: 1,
      contextToken: prepared.contextToken,
    }).catch(() => {});
  }

  schedulePendingImageInboundFlush(scopeKey, bindingKey, workspaceRoot, delayMs = INBOUND_IMAGE_BATCH_IDLE_MS) {
    const draft = this.pendingImageInboundByScope.get(scopeKey);
    if (!draft) {
      return;
    }
    if (draft.timer) {
      clearTimeout(draft.timer);
    }
    draft.timer = setTimeout(() => {
      void this.flushPendingImageInboundBatch({ bindingKey, workspaceRoot }).catch((error) => {
        const message = error instanceof Error ? error.stack || error.message : String(error);
        console.error(`[cyberboss] image inbound debounce flush failed ${message}`);
      });
    }, Math.max(0, Number(delayMs) || 0));
    this.pendingImageInboundByScope.set(scopeKey, draft);
  }

  clearPendingImageInboundTimer(scopeKey) {
    const draft = this.pendingImageInboundByScope.get(scopeKey);
    if (!draft?.timer) {
      return;
    }
    clearTimeout(draft.timer);
    draft.timer = null;
  }

  clearPendingImageInboundTimers() {
    for (const [scopeKey] of this.pendingImageInboundByScope.entries()) {
      this.clearPendingImageInboundTimer(scopeKey);
    }
  }

  async flushPendingImageInboundBatch({ bindingKey = "", workspaceRoot = "", trailingPrepared = null } = {}) {
    const scopeKey = buildScopeKey(bindingKey, workspaceRoot);
    const draft = scopeKey ? this.pendingImageInboundByScope.get(scopeKey) || null : null;
    if (!draft?.bindingKey || !draft?.workspaceRoot) {
      if (scopeKey) {
        this.pendingImageInboundByScope.delete(scopeKey);
      }
      return false;
    }

    this.clearPendingImageInboundTimer(scopeKey);
    this.pendingImageInboundByScope.delete(scopeKey);

    const queued = Array.isArray(draft.messages)
      ? draft.messages
        .filter((message) => message && typeof message === "object")
        .slice()
        .sort(comparePendingInboundMessages)
      : [];
    if (!queued.length) {
      return false;
    }

    const { batchMessages, remainingMessages } = takeImageOnlyBatchMessages(queued, MAX_INBOUND_STICKER_IMAGE_BATCH);
    if (!batchMessages.length) {
      return false;
    }

    if (remainingMessages.length) {
      this.pendingImageInboundByScope.set(scopeKey, {
        bindingKey: draft.bindingKey,
        workspaceRoot: draft.workspaceRoot,
        messages: remainingMessages,
        timer: null,
      });
    }

    const prepared = buildMergedInboundPrepared({
      bindingKey: draft.bindingKey,
      workspaceRoot: draft.workspaceRoot,
      messages: batchMessages,
      trailingPrepared,
    });
    await this.routePreparedInbound({
      bindingKey: draft.bindingKey,
      workspaceRoot: draft.workspaceRoot,
      prepared,
    });

    if (remainingMessages.length) {
      await this.flushPendingImageInboundBatch({
        bindingKey: draft.bindingKey,
        workspaceRoot: draft.workspaceRoot,
      });
    }

    return true;
  }

  bufferPendingInboundMessage({ bindingKey, workspaceRoot, prepared }) {
    const scopeKey = buildScopeKey(bindingKey, workspaceRoot);
    if (!scopeKey || !prepared) {
      return;
    }

    const current = this.pendingInboundByScope.get(scopeKey) || {
      bindingKey,
      workspaceRoot,
      messages: [],
    };
    current.messages.push({
      workspaceId: prepared.workspaceId,
      accountId: prepared.accountId,
      senderId: prepared.senderId,
      messageId: prepared.messageId,
      contextToken: prepared.contextToken,
      provider: prepared.provider,
      originalText: prepared.originalText,
      text: prepared.text,
      attachments: Array.isArray(prepared.attachments) ? prepared.attachments : [],
      attachmentFailures: Array.isArray(prepared.attachmentFailures) ? prepared.attachmentFailures : [],
      receivedAt: prepared.receivedAt,
    });
    this.pendingInboundByScope.set(scopeKey, current);
    void this.channelAdapter.sendTyping({
      userId: prepared.senderId,
      status: 1,
      contextToken: prepared.contextToken,
    }).catch(() => {});
  }

  hasPendingInboundMessage(bindingKey, workspaceRoot) {
    return this.pendingInboundByScope.has(buildScopeKey(bindingKey, workspaceRoot));
  }

  async flushPendingInboundMessages({ bindingKey = "", workspaceRoot = "", ignoreBoundary = false } = {}) {
    const targetScopeKey = buildScopeKey(bindingKey, workspaceRoot);
    const scopeEntries = targetScopeKey
      ? [[targetScopeKey, this.pendingInboundByScope.get(targetScopeKey) || null]]
      : [...this.pendingInboundByScope.entries()];

    for (const [scopeKey, draft] of scopeEntries) {
      if (!draft?.bindingKey || !draft?.workspaceRoot) {
        this.pendingInboundByScope.delete(scopeKey);
        continue;
      }
      if (this.isTurnDispatchBlocked(draft.bindingKey, draft.workspaceRoot, { ignoreBoundary })) {
        continue;
      }
      const pendingDispatch = this.mergePendingInboundDraft(draft);
      if (!pendingDispatch?.prepared) {
        this.pendingInboundByScope.delete(scopeKey);
        continue;
      }
      this.pendingInboundByScope.delete(scopeKey);
      const dispatched = await this.dispatchPreparedTurn({
        bindingKey: pendingDispatch.prepared.bindingKey,
        workspaceRoot: pendingDispatch.prepared.workspaceRoot,
        prepared: {
          workspaceId: pendingDispatch.prepared.workspaceId,
          accountId: pendingDispatch.prepared.accountId,
          senderId: pendingDispatch.prepared.senderId,
          contextToken: pendingDispatch.prepared.contextToken,
          provider: pendingDispatch.prepared.provider,
          originalText: pendingDispatch.prepared.originalText,
          text: pendingDispatch.prepared.text,
          attachments: pendingDispatch.prepared.attachments,
          attachmentFailures: pendingDispatch.prepared.attachmentFailures,
          receivedAt: pendingDispatch.prepared.receivedAt,
        },
      });
      if (!dispatched) {
        this.pendingInboundByScope.set(scopeKey, draft);
        continue;
      }
      if (pendingDispatch.remainingMessages.length) {
        this.pendingInboundByScope.set(scopeKey, {
          bindingKey: draft.bindingKey,
          workspaceRoot: draft.workspaceRoot,
          messages: pendingDispatch.remainingMessages,
        });
      }
    }
  }

  mergePendingInboundDraft(draft) {
    const queued = Array.isArray(draft?.messages)
      ? draft.messages
        .filter((message) => message && typeof message === "object")
        .slice()
        .sort(comparePendingInboundMessages)
      : [];
    if (!queued.length) {
      return null;
    }
    if (queued.every((message) => shouldBatchImageOnlyInbound(message))) {
      const { batchMessages, remainingMessages } = takeImageOnlyBatchMessages(queued, MAX_INBOUND_STICKER_IMAGE_BATCH);
      return {
        prepared: buildMergedInboundPrepared({
          bindingKey: draft.bindingKey,
          workspaceRoot: draft.workspaceRoot,
          messages: batchMessages,
        }),
        remainingMessages,
      };
    }

    if (queued.length === 1) {
      return {
        prepared: {
          bindingKey: draft.bindingKey,
          workspaceRoot: draft.workspaceRoot,
          ...queued[0],
        },
        remainingMessages: [],
      };
    }

    const latest = queued[queued.length - 1];
    const blocks = queued
      .map((message) => String(message.text || "").trim())
      .filter(Boolean);

    return {
      prepared: {
        bindingKey: draft.bindingKey,
        workspaceRoot: draft.workspaceRoot,
        ...latest,
        text: [
          "Multiple newer WeChat messages arrived while you were still handling the previous turn.",
          "Treat the following blocks as one ordered batch of fresh user input and respond once after considering all of them.",
          "",
          blocks.join("\n\n"),
        ].join("\n").trim(),
      },
      remainingMessages: [],
    };
  }

  async prepareIncomingMessageForRuntime(normalized, workspaceRoot) {
    if (normalized?.provider === "system") {
      return {
        ...normalized,
        originalText: normalized.text,
        text: String(normalized.text || "").trim(),
        attachments: [],
        attachmentFailures: [],
      };
    }

    const attachments = Array.isArray(normalized.attachments) ? normalized.attachments : [];
    if (!attachments.length) {
      return buildInboundDraft(normalized);
    }

    const persisted = await persistIncomingWeixinAttachments({
      attachments,
      stateDir: this.config.stateDir,
      cdnBaseUrl: this.config.weixinCdnBaseUrl,
      messageId: normalized.messageId,
      receivedAt: normalized.receivedAt,
    });

    if (!persisted.saved.length && persisted.failed.length && !String(normalized.text || "").trim()) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `⚠️ Failed to receive image or attachment\n${persisted.failed.map((item) => item.reason).join("\n")}`,
        contextToken: normalized.contextToken,
        preserveBlock: true,
      }).catch(() => {});
      return null;
    }

    // 记账失败绝不能影响收图这件事本身——文件已经在磁盘上了。
    if (typeof this.recordIncomingMedia === "function") {
      this.recordIncomingMedia(persisted.saved, normalized);
    }

    const prepared = buildInboundDraft(normalized, {
      attachments: persisted.saved,
      attachmentFailures: persisted.failed,
    });
    if (!prepared.originalText && !prepared.attachments.length && prepared.attachmentFailures.length) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `⚠️ Failed to receive image or attachment\n${persisted.failed.map((item) => item.reason).join("\n")}`,
        contextToken: normalized.contextToken,
        preserveBlock: true,
      }).catch(() => {});
      return null;
    }

    return prepared;
  }

  async flushPendingSystemMessages() {
    const pendingMessages = this.systemMessageDispatcher?.drainPending() || [];
    for (const message of pendingMessages) {
      try {
        // 不是主人的主动消息，走**普通用户那条模型路径**。
        //
        // dispatchSystemMessage 出口是主人的 Codex，开头有一道 owner-only 闸门。
        // 访客的主动消息走进去必然被挡回来——那样「每个人自己的主动找我」就是
        // 一个存了、显示了、但永远不会发生的设置。这是这个仓最熟悉的那种坏。
        if (await this.dispatchGuestCheckin(message)) {
          continue;
        }
        const dispatched = await this.dispatchSystemMessage(message);
        if (!dispatched) {
          this.requeueSystemMessage(message);
        }
      } catch {
        this.requeueSystemMessage(message);
      }
    }
  }

  // 重排一条投不出去的系统消息，但**有上限**。
  //
  // 无限重排看起来最安全，实际最危险：一条永远投不出去的消息会让
  // hasPendingForAccount 对它那个号永远为真，轮询器于是每一轮都跳过那个号下面
  // 的所有人。那个号从此彻底静默，而且没有任何东西会报错——你只会发现"它只找
  // 我一个人"，然后查一整天。丢掉一条主动打招呼的代价，远小于让一个号哑掉。
  requeueSystemMessage(message) {
    const attempts = Number(message?.attempts || 0) + 1;
    if (attempts >= SYSTEM_MESSAGE_MAX_ATTEMPTS) {
      console.warn(
        `[cyberboss] system message dropped after ${attempts} attempts`
        + ` account=${message?.accountId} to=${String(message?.senderId || "").slice(0, 10)}…`,
      );
      return;
    }
    try {
      this.systemMessageDispatcher?.requeue({ ...message, attempts });
    } catch {
      // 重排都失败就让它掉地上，不能反过来把这一轮也搞挂。
    }
  }

  // 访客的主动消息。返回 true 表示这条已经办掉了。
  //
  // 主人走 Codex（有工具、有工作区）；访客走 runUserModelTurn（预算、熔断、
  // provider router，前 N 个人共用主人那把钥匙）。两条路本来就分开，主动消息
  // 也必须按同一条线分，否则访客那一半永远发不出去。
  async dispatchGuestCheckin(message) {
    const senderId = String(message?.senderId || "").trim();
    if (!senderId || !this.userAdmission) {
      return false;
    }
    // 先做一次**只读**的身份查询，查不到就不往下走。
    //
    // admit() 不是只读的：认不出来的人它会当新人**注册**。而主动消息这条路上，
    // message.accountId 有可能是错的——resolveAccountForUser 在那个人的号已经
    // 消失时会退回主号。于是「给他发个问候」变成了「以主号的名义给他开一个新
    // 户口」：2026-07-30 06:26:18 那一次就这么造出了 usr_w6cEq-n6，把同一个人
    // 劈成了三个 user_id（原号一个、主号一个、新号一个），记忆和待办各留一份。
    //
    // 主动消息只该找**已经认识的人**。不认识就跳过，注册是入站那条路的事——
    // 那里的 accountId 来自消息本身，是可信的。
    const known = this.userAdmission.users?.resolveByPrincipal?.({
      channel: "weixin",
      botAccountRef: message.accountId,
      senderRef: senderId,
    });
    if (!known) {
      console.warn(
        `[cyberboss] checkin skipped unknown_principal account=${message.accountId}`
        + ` to=${senderId.slice(0, 10)}…（这个号下面没有这个人，不替他注册）`,
      );
      return true;
    }
    let decision;
    try {
      decision = this.userAdmission.admit({
        botAccountRef: message.accountId,
        senderRef: senderId,
        text: String(message.text || ""),
      });
    } catch {
      return false;
    }
    // 主人的照旧走 Codex。
    if (decision?.route !== "user" || !decision.userContext) {
      return false;
    }
    const normalized = {
      senderId,
      accountId: message.accountId,
      contextToken: this.channelAdapter.getKnownContextTokens()[senderId] || "",
      // 给模型的是**带指令的**那一段，不是那句光秃秃的内部触发语。
      //
      // 原来这里直接把 "Linz comes to mind again." 丢给模型：一句没头没尾的英文，
      // 而且 %USER% 填的是**主人**的名字（buildCheckinTrigger 读的是 config 里
      // 主人那一份），访客那边看到的是一个跟他无关的人名。模型于是写出一篇
      // 527 字的长文——主人自己那条路的回复只有 13~31 字，因为它带着
      // 「one short natural WeChat message」这句指令。
      //
      // 长文的代价不是啰嗦，是**发不出去**：长文会被切成多片，而微信的
      // context_token 只允许有限次回复，片数一超就整条失败（
      // WEIXIN_PROVIDER_ERROR）。2026-07-30 06:36 那条就是这么挂的，同一个人
      // 同一个号，400 字那条发得出去，527 字这条发不出去。
      text: buildGuestCheckinPrompt(),
      provider: "system",
    };
    if (!normalized.contextToken) {
      // 投不出去就别唤醒模型：花了额度，消息还是发不到他手上。
      //
      // 但必须**说一声**。原来这里是一句 return true，静悄悄把消息丢掉——
      // 2026-07-30 就是这样：一个人的号被换掉了（旧号的 .json 没了，只剩一个
      // 孤零零的 context-tokens 文件），他的 token 从此加载不到，每一条主动
      // 消息都在这里无声无息地消失。日志里一个字都没有，只能看出"他就是收不到"。
      console.warn(
        `[cyberboss] checkin dropped no_context_token account=${message.accountId}`
        + ` to=${senderId.slice(0, 10)}…（这个人的号可能被换过，等他再发一条消息就会恢复）`,
      );
      return true;
    }
    try {
      await this.runUserModelTurn(normalized, decision.userContext);
    } catch (error) {
      console.error(
        `[cyberboss] 访客的主动消息失败 code=${normalizeErrorCode(error?.code) || "guest_checkin_failed"}`,
      );
    }
    return true;
  }

  async flushPendingTimelineScreenshots() {
    const pendingJobs = this.liveAccountIds()
      .flatMap((accountId) => this.timelineScreenshotQueue.drainForAccount(accountId));
    for (const job of pendingJobs) {
      try {
        const captured = await this.projectServices.timeline.captureScreenshot({
          outputFile: job.outputFile,
          selector: job.selector,
          range: job.range,
          date: job.date,
          week: job.week,
          month: job.month,
          category: job.category,
          subcategory: job.subcategory,
          width: job.width,
          height: job.height,
          sidePadding: job.sidePadding,
          locale: job.locale,
        });
        await this.sendLocalFileToCurrentChat({
          senderId: job.senderId,
          filePath: captured.outputFile,
        });
      } catch (error) {
        const messageText = error instanceof Error ? error.message : String(error || "unknown error");
        console.error(`[cyberboss] timeline screenshot failed job=${job.id} ${messageText}`);
        await this.channelAdapter.sendTyping({
          userId: job.senderId,
          status: 0,
        }).catch(() => {});
        await this.channelAdapter.sendText({
          userId: job.senderId,
          text: `❌ Timeline screenshot failed\n${messageText}`,
          preserveBlock: true,
        }).catch(() => {});
      }
    }
  }

  resolveLongPollTimeoutMs() {
    if (this.systemMessageDispatcher?.hasPending()) {
      return MIN_LONG_POLL_TIMEOUT_MS;
    }
    if (this.liveAccountIds().some(
      (accountId) => this.timelineScreenshotQueue.hasPendingForAccount(accountId),
    )) {
      return MIN_LONG_POLL_TIMEOUT_MS;
    }

    const nextDueAtMs = this.reminderQueue.peekNextDueAtMs();
    if (!nextDueAtMs) {
      return DEFAULT_LONG_POLL_TIMEOUT_MS;
    }

    const remainingMs = nextDueAtMs - Date.now();
    if (remainingMs <= MIN_LONG_POLL_TIMEOUT_MS) {
      return MIN_LONG_POLL_TIMEOUT_MS;
    }
    return Math.max(MIN_LONG_POLL_TIMEOUT_MS, Math.min(DEFAULT_LONG_POLL_TIMEOUT_MS, remainingMs));
  }

  // 所有归这个进程管的号一起刷。以前只刷主号那一个，第二个号下面的人
  // 定的提醒会永远躺在队列里到不了点。
  async flushDueReminders() {
    const accountIds = new Set(this.liveAccountIds());
    const dueReminders = this.reminderQueue
      .listDue(Date.now())
      .filter((reminder) => accountIds.has(reminder.accountId));

    for (const reminder of dueReminders) {
      // 「X 分钟后提醒我」定下来的那种，到点直接发，不唤醒模型。
      //
      // 走模型有两个问题：一是它可能又决定"这次不说"（主动打招呼那条路每五分钟
      // 就这么静默一次），二是普通用户根本进不去主人的 Codex。而提醒是主人明确
      // 要求过的事，**没有任何重新判断的余地**——到点就得响。
      if (reminder.direct) {
        await this.deliverDirectReminder(reminder);
        continue;
      }
      try {
        this.systemMessageQueue.enqueue({
          id: `reminder:${reminder.id}`,
          accountId: reminder.accountId,
          senderId: reminder.senderId,
          workspaceRoot: this.resolveReminderWorkspaceRoot(reminder),
          text: buildReminderSystemTrigger(reminder, this.config),
          createdAt: new Date().toISOString(),
        });
      } catch {
        this.reminderQueue.enqueue({
          ...reminder,
          dueAtMs: Date.now() + 5_000,
        });
      }
    }
  }

  // 到点了，把当初那句话发回去。零模型、零 token。
  //
  // 发失败要重排，别默默丢掉：主人定了提醒又没等到，比一开始就说"我做不到"
  // 伤得多。重排三次还不行就放弃，并且在后台那一栏留一条看得见的记录。
  async deliverDirectReminder(reminder) {
    try {
      await this.channelAdapter.sendText({
        userId: reminder.senderId,
        text: reminder.text,
        accountId: reminder.accountId,
        contextToken: reminder.contextToken,
      });
      this.noteDirectReply(reminder.senderId, reminder.text, { delivered: true });
      this.noteForDashboard("一条提醒到点发出去了");
    } catch (error) {
      const attempts = Number(reminder.attempts) || 0;
      const code = String(error?.code || "");
      const errorClass = /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(code) ? code : "send_failed";
      if (attempts < 3) {
        this.reminderQueue.enqueue({
          ...reminder,
          dueAtMs: Date.now() + 30_000,
          attempts: attempts + 1,
        });
        return;
      }
      console.error(`[cyberboss] 提醒发不出去，放弃 原因=${errorClass}`);
      this.noteDirectReply(reminder.senderId, reminder.text, {
        delivered: false,
        errorClass,
      });
      this.noteForDashboard("有一条提醒到点了但没发出去");
    }
  }

  resolveReminderWorkspaceRoot(reminder) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: this.config.workspaceId,
      accountId: reminder.accountId,
      senderId: reminder.senderId,
    });
    return this.resolveWorkspaceRoot(bindingKey);
  }

  async dispatchSystemMessage(message) {
    // 记一下这一轮是哪一类。streamDelivery 那一层只知道"这是一条系统回复"，
    // 分不出主动打招呼和到点提醒——而面板上这两件事对主人的意义完全不同。
    // flushDueReminders 排队时用的 id 前缀就是唯一的线索。
    this.activeSystemMessageKind = String(message?.id || "").startsWith("reminder:")
      ? "reminder"
      : "checkin";
    const prepared = this.systemMessageDispatcher?.buildPreparedMessage(message, this.channelAdapter.getKnownContextTokens()[message.senderId] || "");
    if (!prepared) {
      throw new Error("system message could not be prepared");
    }
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: prepared.workspaceId,
      accountId: prepared.accountId,
      senderId: prepared.senderId,
    });
    const workspaceRoot = this.workspaceRegistry.assertAllowedRoot(
      prepared.workspaceRoot || this.resolveWorkspaceRoot(bindingKey)
    ).root;
    if (this.isTurnDispatchBlocked(bindingKey, workspaceRoot)) {
      return false;
    }
    return this.dispatchPreparedTurn({ bindingKey, workspaceRoot, prepared });
  }

  async dispatchChannelCommand(normalized, command) {
    switch (command.name) {
      case "bind":
        await this.handleBindCommand(normalized, command);
        return;
      case "status":
        await this.handleStatusCommand(normalized);
        return;
      case "new":
        await this.handleNewCommand(normalized);
        return;
      case "reread":
        await this.handleRereadCommand(normalized);
        return;
      case "compact":
        await this.handleCompactCommand(normalized);
        return;
      case "switch":
        await this.handleSwitchCommand(normalized, command);
        return;
      case "stop":
        await this.handleStopCommand(normalized);
        return;
      case "checkin":
        await this.handleCheckinCommand(normalized, command);
        return;
      case "chunk":
        await this.handleChunkCommand(normalized, command);
        return;
      case "yes":
      case "always":
      case "no":
        // 批准一条待审批 = 批准在主人的机器上真的跑那条命令，而「always」还会把
        // 它写进工作区永久白名单。所以这里的门槛是 shell.execute，不是「能不能
        // 发消息」。
        //
        // activeUserContext 为 null 只在多用户准入整个关掉时发生（见
        // admitInboundMessage 的 route:"owner" 分支），那种形态下全机就主人一个
        // 人，不能因为没有 context 就把他自己的审批挡在外面。有 context 就必须
        // 真的过闸门——那是唯一能出现访客的形态。
        if (this.activeUserContext && !this.activeUserContext.may("shell.execute")) {
          await this.channelAdapter.sendText({
            userId: normalized.senderId,
            text: "这条命令要在主人的机器上执行，只有主人能批准。",
            contextToken: normalized.contextToken,
          });
          console.warn(
            `[cyberboss] approval refused non_owner command=${command.name}`,
          );
          return;
        }
        await this.handleApprovalCommand(normalized, command);
        return;
      case "model":
        await this.handleModelCommand(normalized, command);
        return;
      case "star":
        await this.handleStarCommand(normalized);
        return;
      case "help":
        await this.handleHelpCommand(normalized);
        return;
      default:
        await this.channelAdapter.sendText({
          userId: normalized.senderId,
          text: buildWeixinHelpText(),
          contextToken: normalized.contextToken,
        });
    }
  }

  async handleBindCommand(normalized, command) {
    const workspaceAlias = normalizeCommandArgument(command.args);
    if (!workspaceAlias) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 Usage: /bind <workspace-alias>",
        contextToken: normalized.contextToken,
      });
      return;
    }

    let workspace;
    try {
      workspace = this.workspaceRegistry.resolve(workspaceAlias);
    } catch (error) {
      const code = error instanceof WorkspaceRegistryError
        ? error.code
        : "workspace_resolution_failed";
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `⚠️ Workspace alias rejected (${code}).`,
        contextToken: normalized.contextToken,
      });
      return;
    }

    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    this.runtimeAdapter.getSessionStore().setActiveWorkspaceRoot(bindingKey, workspace.root);
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `✅ Workspace bound\nworkspace: ${workspace.alias}`,
      contextToken: normalized.contextToken,
    });
  }

  async handleStatusCommand(normalized) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const threadId = sessionStore.getThreadIdForWorkspace(bindingKey, workspaceRoot);
    const threadState = threadId ? this.threadStateStore.getThreadState(threadId) : null;
    const runtimeName = this.runtimeAdapter.describe().id || "runtime";
    const context = threadState?.context?.runtimeId === runtimeName
      ? threadState.context
      : this.threadStateStore.getLatestContext(runtimeName);
    const runtimeParams = sessionStore.getRuntimeParamsForWorkspace(bindingKey, workspaceRoot);
    const storedModel = runtimeParams.model || "";
    const storedModelProvider = runtimeParams.modelProvider || this.runtimeAdapter.describe().modelProvider || "";
    const effectiveModel = this.runtimeAdapter.describe().model || storedModel;
    const schedulerStatus = this.jobScheduler
      ? this.jobScheduler.statusSnapshot()
      : null;
    const outboxStatus = this.outboxWorker
      ? this.outboxWorker.statusSnapshot()
      : null;

    const lines = [
      `📍 workspace: ${this.workspaceRegistry.aliasForRoot(workspaceRoot)}`,
      `🧵 thread: ${schedulerStatus
        ? (threadId ? "(present)" : "(none)")
        : (threadId || "(none)")}`,
      `📊 status: ${threadState?.status || "idle"}`,
      `🤖 runtime: ${runtimeName}`,
      `🤖 model: ${effectiveModel || "(default)"}`,
      `🤖 provider: ${storedModelProvider || "(default)"}`,
    ];
    if (schedulerStatus) {
      lines.push(
        `📥 queue: ${schedulerStatus.queuedTotal}`,
        `🔒 active runtime lease: ${schedulerStatus.activeRuntimeLeaseCount}`,
        `🛡️ gate: ${schedulerStatus.gateState}/${schedulerStatus.gateReason}`,
        `🧭 action: ${schedulerStatus.gateAction}`,
      );
    }
    if (outboxStatus) {
      lines.push(
        `📤 outbox pending: ${outboxStatus.metrics.pending + outboxStatus.metrics.retry}`,
        `✅ outbox confirmed: ${outboxStatus.metrics.confirmed}`,
        `⚠️ outbox failed: ${outboxStatus.metrics.failedTerminal}`,
        `❓ outbox ambiguous: ${outboxStatus.metrics.ambiguous}`,
      );
    }
    lines.push(formatContextStatusLine({
      runtimeName,
      context,
      claudeContextWindow: this.config.claudeContextWindow,
      claudeMaxOutputTokens: this.config.claudeMaxOutputTokens,
    }));
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: lines.join("\n"),
      contextToken: normalized.contextToken,
    });
  }

  async handleNewCommand(normalized) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    if (typeof this.runtimeAdapter.startFreshThreadDraft === "function") {
      await this.runtimeAdapter.startFreshThreadDraft({ bindingKey, workspaceRoot });
    }
    this.runtimeAdapter.getSessionStore().clearThreadIdForWorkspace(bindingKey, workspaceRoot);
    const workspaceLabel = this.workspaceRegistry
      ? this.workspaceRegistry.aliasForRoot(workspaceRoot)
      : workspaceRoot;
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `✅ Switched to a fresh thread draft\nworkspace: ${workspaceLabel}`,
      contextToken: normalized.contextToken,
    });
  }

  async handleRereadCommand(normalized) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const threadId = sessionStore.getThreadIdForWorkspace(bindingKey, workspaceRoot);
    if (!threadId) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 There is no active thread yet. Send a normal message first.",
        contextToken: normalized.contextToken,
      });
      return;
    }

    try {
      this.streamDelivery.queueReplyTargetForThread(threadId, {
        userId: normalized.senderId,
        contextToken: normalized.contextToken,
        provider: normalized.provider,
      });
      const runtimeParams = sessionStore.getRuntimeParamsForWorkspace(bindingKey, workspaceRoot);
      await this.runtimeAdapter.refreshThreadInstructions({
        threadId,
        workspaceRoot,
        model: runtimeParams.model,
        modelProvider: runtimeParams.modelProvider,
      });
    } catch (error) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `❌ Reread failed\n${error instanceof Error ? error.message : String(error || "unknown error")}`,
        contextToken: normalized.contextToken,
      }).catch(() => {});
    }
  }

  async handleCompactCommand(normalized) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const threadId = sessionStore.getThreadIdForWorkspace(bindingKey, workspaceRoot);
    if (!threadId) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 There is no active thread yet. Send a normal message first.",
        contextToken: normalized.contextToken,
      });
      return;
    }

    try {
      this.streamDelivery.queueReplyTargetForThread(threadId, {
        userId: normalized.senderId,
        contextToken: normalized.contextToken,
        provider: normalized.provider,
      });
      await this.runtimeAdapter.compactThread({
        threadId,
        workspaceRoot,
        model: sessionStore.getRuntimeParamsForWorkspace(bindingKey, workspaceRoot).model,
      }).then((result) => {
        const compactTurnId = normalizeCommandArgument(result?.turnId);
        if (compactTurnId) {
          this.pendingOperationByRunKey.set(buildRunKey(threadId, compactTurnId), {
            kind: "compact",
            userId: normalized.senderId,
            contextToken: normalized.contextToken,
          });
        }
      });
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `🗜️ Compact request sent\nthread: ${threadId}`,
        contextToken: normalized.contextToken,
      });
    } catch (error) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `❌ Compact failed\n${error instanceof Error ? error.message : String(error || "unknown error")}`,
        contextToken: normalized.contextToken,
      }).catch(() => {});
    }
  }

  async handleSwitchCommand(normalized, command) {
    const targetThreadId = normalizeThreadId(command.args);
    if (!targetThreadId) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 Usage: /switch <threadId>",
        contextToken: normalized.contextToken,
      });
      return;
    }

    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const runtimeParams = sessionStore.getRuntimeParamsForWorkspace(bindingKey, workspaceRoot);
    const resumed = await this.runtimeAdapter.resumeThread({
      threadId: targetThreadId,
      workspaceRoot,
      model: runtimeParams.model,
      modelProvider: runtimeParams.modelProvider,
    });
    sessionStore.setThreadIdForWorkspace(
      bindingKey,
      workspaceRoot,
      resumed?.threadId || targetThreadId,
    );
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `✅ Thread switched\nworkspace: ${workspaceRoot}\nthread: ${resumed?.threadId || targetThreadId}`,
      contextToken: normalized.contextToken,
    });
  }

  async handleStopCommand(normalized) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const threadId = this.runtimeAdapter.getSessionStore().getThreadIdForWorkspace(bindingKey, workspaceRoot);
    const threadState = threadId ? this.threadStateStore.getThreadState(threadId) : null;
    if (!threadId || !threadState?.turnId || !["running", "waiting_approval"].includes(threadState.status)) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 There is no running thread right now.",
        contextToken: normalized.contextToken,
      });
      return;
    }

    await this.runtimeAdapter.cancelTurn({
      threadId,
      turnId: threadState.turnId,
      workspaceRoot,
    });
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `⏹️ Stop request sent\nthread: ${threadId}`,
      contextToken: normalized.contextToken,
    });
  }

  async handleCheckinCommand(normalized, command) {
    const rangeInput = normalizeCommandArgument(command.args);
    if (!rangeInput) {
      const currentRange = this.checkinConfigStore.getRange(resolveDefaultCheckinRange());
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `⏰ Current check-in interval is ${Math.round(currentRange.minIntervalMs / 60000)}-${Math.round(currentRange.maxIntervalMs / 60000)} minutes.`,
        contextToken: normalized.contextToken,
      });
      return;
    }

    const parsedRange = parseCheckinRangeMinutes(rangeInput);
    if (!parsedRange) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 Usage: /checkin <min>-<max>",
        contextToken: normalized.contextToken,
      });
      return;
    }

    this.checkinConfigStore.setRange({
      minIntervalMs: parsedRange.minMinutes * 60_000,
      maxIntervalMs: parsedRange.maxMinutes * 60_000,
    });
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `✅ Check-in interval reset to ${parsedRange.minMinutes}-${parsedRange.maxMinutes} minutes and will apply on the next polling cycle.`,
      contextToken: normalized.contextToken,
    });
  }

  async handleChunkCommand(normalized, command) {
    const arg = normalizeCommandArgument(command.args);
    if (!arg) {
      const current = this.channelAdapter.getMinChunkChars?.() ?? DEFAULT_MIN_WEIXIN_CHUNK;
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `💡 Current minimum merge chunk is ${current} characters. Usage: /chunk <number> (e.g. /chunk 50)`,
        contextToken: normalized.contextToken,
      });
      return;
    }
    const parsed = Number.parseInt(arg, 10);
    if (!Number.isFinite(parsed) || parsed < 1 || parsed > MAX_MIN_WEIXIN_CHUNK) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `⚠️  Invalid value. Please provide a number between 1 and ${MAX_MIN_WEIXIN_CHUNK}.`,
        contextToken: normalized.contextToken,
      });
      return;
    }
    const updated = this.channelAdapter.setMinChunkChars?.(parsed) ?? parsed;
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `✅ Minimum merge chunk set to ${updated} characters. Shorter fragments will be merged into one message up to this size.`,
      contextToken: normalized.contextToken,
    });
  }

  async handleApprovalCommand(normalized, command) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const threadId = this.runtimeAdapter.getSessionStore().getThreadIdForWorkspace(bindingKey, workspaceRoot);
    const threadState = threadId ? this.threadStateStore.getThreadState(threadId) : null;
    const approval = threadState?.pendingApproval || null;
    if (!threadId || approval?.requestId == null || String(approval.requestId).trim() === "") {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "💡 There is no pending approval request right now.",
        contextToken: normalized.contextToken,
      });
      return;
    }

    const approvalResponse = buildApprovalResponsePayload(approval, command.name);
    if (!approvalResponse) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: "⚠️ This Codex MCP request cannot be answered from WeChat yet.",
        contextToken: normalized.contextToken,
      });
      return;
    }
    console.log(
      `[cyberboss] approval response requested thread=${threadId} requestId=${approval.requestId} mode=${approvalResponse.result ? "result" : "decision"} workspace=${workspaceRoot}`
    );
    await this.runtimeAdapter.respondApproval(approvalResponse);
    this.runtimeAdapter.getSessionStore().clearApprovalPrompt(threadId);
    console.log(
      `[cyberboss] approval response delivered thread=${threadId} requestId=${approval.requestId}`
    );
    if (command.name === "always" && isApprovalAcceptResponse(approvalResponse)) {
      this.runtimeAdapter.getSessionStore().rememberApprovalPrefixForWorkspace(workspaceRoot, approval.commandTokens);
    }
    this.threadStateStore.resolveApproval(threadId, "running");
    const text = buildApprovalResponseText(approval, command.name, approvalResponse);
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text,
      contextToken: normalized.contextToken,
    });
  }

  async handleModelCommand(normalized, command) {
    const bindingKey = this.runtimeAdapter.getSessionStore().buildBindingKey({
      workspaceId: normalized.workspaceId,
      accountId: normalized.accountId,
      senderId: normalized.senderId,
    });
    const workspaceRoot = this.resolveWorkspaceRoot(bindingKey);
    const query = normalizeCommandArgument(command.args);
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const catalog = sessionStore.getAvailableModelCatalog();
    const currentModel = sessionStore.getRuntimeParamsForWorkspace(bindingKey, workspaceRoot).model;

    if (!query) {
      const lines = [
        `Current model: ${currentModel || "(default)"}`,
      ];
      if (catalog?.models?.length) {
        lines.push(`Available models: ${catalog.models.map((item) => item.model).join(", ")}`);
      } else {
        lines.push("Available models: (not available)");
      }
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: lines.join("\n"),
        contextToken: normalized.contextToken,
      });
      return;
    }

    const runtimeId = this.runtimeAdapter.describe().id || "runtime";
    let matched = findModelByQuery(catalog?.models || [], query);
    if (!matched && runtimeId !== "codex" && !catalog?.models?.length) {
      matched = { model: query };
    }
    if (!matched) {
      await this.channelAdapter.sendText({
        userId: normalized.senderId,
        text: `❌ Model not found\n${query}`,
        contextToken: normalized.contextToken,
      });
      return;
    }

    sessionStore.setRuntimeParamsForWorkspace(bindingKey, workspaceRoot, {
      model: matched.model,
    });
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: `✅ Model switched\nworkspace: ${workspaceRoot}\nmodel: ${matched.model}`,
      contextToken: normalized.contextToken,
    });
  }

  async handleStarCommand(normalized) {
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: [
        "📦 This deployment uses the fixed local MetaDatabase source bundle.",
        "No upstream clone, sync, support, endorsement, or star target is configured.",
        "Original licenses, provenance, source, modifications, and unresolved conflict records are preserved locally.",
      ].join("\n"),
      contextToken: normalized.contextToken,
    });
  }

  async handleHelpCommand(normalized) {
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text: buildWeixinHelpText(),
      contextToken: normalized.contextToken,
    });
  }

  resolveWorkspaceRoot(bindingKey) {
    const sessionStore = this.runtimeAdapter.getSessionStore();
    return this.workspaceRegistry.assertAllowedRoot(
      sessionStore.getActiveWorkspaceRoot(bindingKey) || this.config.workspaceRoot
    ).root;
  }

  resolveDurableReplyTargetForJob(jobId) {
    if (!this.runtimeSpoolDatabase || !jobId) {
      return null;
    }
    const job = this.runtimeSpoolDatabase.getJob(jobId);
    if (!job?.inbox_id) {
      return null;
    }
    let payloadBuffer = null;
    let contextBuffer = null;
    try {
      payloadBuffer = this.runtimeSpoolDatabase.readInboundPayload(job.inbox_id);
      contextBuffer = this.runtimeSpoolDatabase.readInboundContextToken(
        job.inbox_id,
      );
      const payload = JSON.parse(payloadBuffer.toString("utf8"));
      const userId = normalizeText(payload?.senderId);
      const storedContext = contextBuffer
        ? normalizeText(contextBuffer.toString("utf8"))
        : "";
      const refreshedContext = userId
        ? normalizeText(this.channelAdapter.getKnownContextTokens?.()?.[userId])
        : "";
      return normalizeReplyTarget({
        userId,
        contextToken: storedContext || refreshedContext,
        provider: payload?.provider || "weixin",
      });
    } catch {
      return null;
    } finally {
      payloadBuffer?.fill?.(0);
      contextBuffer?.fill?.(0);
    }
  }

  async handleDurableJobTerminal({
    job,
    event = null,
    terminalStatus = "",
    replyTarget = null,
  } = {}) {
    if (!this.outboxWorker || !this.runtimeSpoolDatabase || !job?.id) {
      return Object.freeze({ handled: false, reason: "outbox_unavailable" });
    }
    const target =
      normalizeReplyTarget(replyTarget)
      || this.resolveDurableReplyTargetForJob(job.id);
    if (!target) {
      return Object.freeze({
        handled: false,
        reason: "reply_target_unavailable",
        state: this.runtimeSpoolDatabase.reconcileJobReplyState(job.id),
      });
    }
    const durableTerminal = ["succeeded", "failed_terminal", "cancelled"].includes(
      terminalStatus,
    )
      ? terminalStatus
      : ["succeeded", "failed_terminal", "cancelled"].includes(job.status)
        ? job.status
        : "failed_terminal";
    const result = await this.outboxWorker.ensureTerminalMessage({
      jobId: job.id,
      terminalStatus: durableTerminal,
      target,
      logicalKey: `terminal:${job.id}:${durableTerminal}`,
      text:
        durableTerminal === "succeeded"
          ? normalizeText(event?.payload?.text) || "✅ Completed."
          : "",
    });
    return Object.freeze({
      handled: true,
      result,
      state: this.runtimeSpoolDatabase.reconcileJobReplyState(job.id),
    });
  }

  async handleRuntimeEvent(event) {
    const schedulerEvent = this.jobScheduler
      ? await this.jobScheduler.handleRuntimeEvent(event)
      : null;
    const terminalReplyTarget = [
      "runtime.turn.completed",
      "runtime.turn.failed",
    ].includes(event?.type)
      && typeof this.streamDelivery.resolveReplyTargetForRun === "function"
      ? this.streamDelivery.resolveReplyTargetForRun({
          threadId: event?.payload?.threadId,
          turnId: event?.payload?.turnId,
        })
      : null;
    await this.streamDelivery.handleRuntimeEvent(event);
    if (!event) {
      return;
    }
    if (event.type === "runtime.turn.completed" || event.type === "runtime.turn.failed") {
      const completedRunKey = buildRunKey(event.payload.threadId, event.payload.turnId);
      const pendingOperations = this.pendingOperationByRunKey;
      const pendingOperation = pendingOperations?.get?.(completedRunKey) || null;
      if (pendingOperation && pendingOperations?.delete) {
        pendingOperations.delete(completedRunKey);
      }
      const sessionStore = this.runtimeAdapter.getSessionStore();
      sessionStore.clearApprovalPrompt(event.payload.threadId);
      const linked = this.runtimeAdapter.getSessionStore().findBindingForThreadId(event.payload.threadId);
      const scopeKey = linked?.bindingKey && linked?.workspaceRoot
        ? buildScopeKey(linked.bindingKey, linked.workspaceRoot)
        : "";
      if (scopeKey) {
        this.turnBoundaryScopeKeys.add(scopeKey);
      }
      try {
        this.turnGateStore.releaseThread(event.payload.threadId);
        if (schedulerEvent?.terminal && this.outboxWorker) {
          await this.handleDurableJobTerminal({
            job: this.runtimeSpoolDatabase.getJob(schedulerEvent.jobId),
            event,
            terminalStatus: schedulerEvent.terminalStatus,
            replyTarget: terminalReplyTarget,
          });
        } else if (event.type === "runtime.turn.failed") {
          await this.sendFailureToThread(
            event.payload.threadId,
            event.payload.text || "❌ Execution failed",
            terminalReplyTarget,
          );
        }
        if (linked?.bindingKey && linked?.workspaceRoot) {
          await this.flushPendingInboundMessages({
            bindingKey: linked.bindingKey,
            workspaceRoot: linked.workspaceRoot,
            ignoreBoundary: true,
          });
        } else {
          await this.flushPendingInboundMessages();
        }
        await this.flushPendingSystemMessages();
        if (pendingOperation?.kind === "compact" && event.type === "runtime.turn.completed") {
          await this.channelAdapter.sendText({
            userId: pendingOperation.userId,
            text: `✅ Compact finished\nthread: ${event.payload.threadId}`,
            contextToken: pendingOperation.contextToken,
          }).catch(() => {});
        }
        const shouldKeepTyping = linked?.bindingKey && linked?.workspaceRoot
          ? (
            this.turnGateStore.isPending(linked.bindingKey, linked.workspaceRoot)
            || this.hasPendingInboundMessage(linked.bindingKey, linked.workspaceRoot)
          )
          : false;
        if (!shouldKeepTyping) {
          await this.stopTypingForThread(event.payload.threadId);
        }
      } finally {
        if (scopeKey) {
          this.turnBoundaryScopeKeys.delete(scopeKey);
        }
      }
      if (schedulerEvent?.terminal) {
        queueMicrotask(() => {
          void this.jobScheduler?.runCycle().catch((error) => {
            console.error(
              `[cyberboss] scheduler continuation failed ${formatErrorMessage(error)}`,
            );
          });
        });
      }
      return;
    }
    if (event.type !== "runtime.approval.requested") {
      return;
    }
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const linked = sessionStore.findBindingForThreadId(event.payload.threadId);
    if (!linked?.workspaceRoot) {
      return;
    }
    const allowlist = sessionStore.getApprovalCommandAllowlistForWorkspace(linked.workspaceRoot);
    const shouldAutoApprove = isAutoApprovedStateDirOperation(event.payload, this.config)
      || matchesBuiltInCommandPrefix(event.payload.commandTokens)
      || matchesCommandPrefix(event.payload.commandTokens, allowlist);
    if (!shouldAutoApprove) {
      const promptState = sessionStore.getApprovalPromptState(event.payload.threadId);
      const promptSignature = buildApprovalPromptSignature(event.payload);
      if (promptState?.signature && promptState.signature === promptSignature) {
        sessionStore.rememberApprovalPrompt(event.payload.threadId, event.payload.requestId, promptSignature);
        console.log(
          `[cyberboss] approval prompt deduped thread=${event.payload.threadId} requestId=${event.payload.requestId}`
        );
        return;
      }
      sessionStore.rememberApprovalPrompt(event.payload.threadId, event.payload.requestId, promptSignature);
      await this.sendApprovalPrompt({
        bindingKey: linked.bindingKey,
        approval: event.payload,
      }).catch((error) => {
        sessionStore.clearApprovalPrompt(event.payload.threadId);
        throw error;
      });
      return;
    }
    const approvalResponse = buildApprovalResponsePayload(event.payload, "yes");
    if (!approvalResponse) {
      sessionStore.clearApprovalPrompt(event.payload.threadId);
      await this.sendApprovalPrompt({
        bindingKey: linked.bindingKey,
        approval: event.payload,
      }).catch(() => {});
      return;
    }
    await this.runtimeAdapter.respondApproval(approvalResponse).catch(() => {});
    this.threadStateStore.resolveApproval(event.payload.threadId, "running");
  }

  async stopTypingForThread(threadId) {
    const linked = this.runtimeAdapter.getSessionStore().findBindingForThreadId(threadId);
    const target = linked?.bindingKey ? this.resolveReplyTargetForBinding(linked.bindingKey) : null;
    if (!target) {
      return;
    }
    await this.channelAdapter.sendTyping({
      userId: target.userId,
      status: 0,
      contextToken: target.contextToken,
    }).catch(() => {});
  }

  async sendFailureToThread(threadId, text, fallbackTarget = null) {
    const linked = this.runtimeAdapter.getSessionStore().findBindingForThreadId(threadId);
    const target = normalizeReplyTarget(
      linked?.bindingKey ? this.resolveReplyTargetForBinding(linked.bindingKey) : null
    ) || normalizeReplyTarget(fallbackTarget);
    if (!target) {
      return;
    }
    await this.channelAdapter.sendText({
      userId: target.userId,
      text: normalizeText(text) || "❌ Execution failed",
      contextToken: target.contextToken,
    }).catch(() => {});
  }

  async sendApprovalPrompt({ bindingKey, approval }) {
    const target = this.resolveReplyTargetForBinding(bindingKey);
    if (!target) {
      console.warn(
        `[cyberboss] approval prompt skipped binding=${bindingKey} requestId=${approval?.requestId || ""} reason=no_reply_target`
      );
      return;
    }
    console.log(
      `[cyberboss] approval prompt sending binding=${bindingKey} user=${target.userId} requestId=${approval?.requestId || ""}`
    );
    await this.channelAdapter.sendTyping({
      userId: target.userId,
      status: 0,
      contextToken: target.contextToken,
    }).catch(() => {});
    await this.channelAdapter.sendText({
      userId: target.userId,
      text: buildApprovalPromptText(approval),
      contextToken: target.contextToken,
      preserveBlock: true,
    });
    console.log(
      `[cyberboss] approval prompt delivered binding=${bindingKey} user=${target.userId} requestId=${approval?.requestId || ""}`
    );
  }

  async restoreBoundThreadSubscriptions() {
    const sessionStore = this.runtimeAdapter.getSessionStore();
    const bindings = sessionStore.listBindings();
    const seenThreadIds = new Set();

    for (const binding of bindings) {
      const bindingKey = normalizeText(binding?.bindingKey);
      if (!bindingKey) {
        continue;
      }

      const target = this.resolveReplyTargetForBinding(bindingKey);
      if (target) {
        this.streamDelivery.setReplyTarget(bindingKey, target);
      }

      for (const workspaceRoot of sessionStore.listWorkspaceRoots(bindingKey)) {
        const normalizedWorkspaceRoot = normalizeCommandArgument(workspaceRoot);
        const normalizedThreadId = normalizeCommandArgument(
          sessionStore.getThreadIdForWorkspace(bindingKey, normalizedWorkspaceRoot)
        );
        if (!normalizedThreadId || seenThreadIds.has(normalizedThreadId)) {
          continue;
        }
        seenThreadIds.add(normalizedThreadId);
        await this.runtimeAdapter.resumeThread({
          threadId: normalizedThreadId,
          workspaceRoot: normalizedWorkspaceRoot,
        }).catch(() => {});
      }
    }
  }

  resolveReplyTargetForBinding(bindingKey) {
    const binding = this.runtimeAdapter.getSessionStore().getBinding(bindingKey) || null;
    const userId = normalizeCommandArgument(binding?.senderId);
    if (!userId) {
      return null;
    }
    const contextToken = this.channelAdapter.getKnownContextTokens()[userId] || "";
    if (!contextToken) {
      return null;
    }
    return {
      userId,
      contextToken,
      provider: "weixin",
    };
  }
}

// The idempotency key for an ordinary-user turn. It is derived from channel
// identifiers only — never from message text — so a redelivery of the same
// WeChat message maps to the same key and is refused as a duplicate, while two
// different messages never collide.
function buildUserTurnRequestId(normalized) {
  const parts = [
    normalizeText(normalized?.accountId),
    normalizeText(normalized?.senderId),
    normalizeText(normalized?.messageId),
  ];
  if (!parts[2]) {
    parts[2] = `${normalizeText(normalized?.receivedAt)}:${crypto.randomUUID()}`;
  }
  return `utr_${crypto.createHash("sha256").update(parts.join(" ")).digest("hex").slice(0, 32)}`;
}

function buildRunKey(threadId, turnId) {
  return `${normalizeCommandArgument(threadId)}:${normalizeCommandArgument(turnId)}`;
}

function normalizeReplyTarget(target) {
  if (!target?.userId || !target?.contextToken) {
    return null;
  }
  return {
    userId: String(target.userId).trim(),
    contextToken: String(target.contextToken).trim(),
    provider: normalizeText(target.provider),
  };
}

function formatCompactNumber(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return "0";
  }
  if (normalized >= 1_000_000) {
    return `${Math.round(normalized / 100_000) / 10}m`;
  }
  if (normalized >= 1_000) {
    return `${Math.round(normalized / 100) / 10}k`;
  }
  return String(Math.round(normalized));
}

function formatContextStatusLine({ runtimeName, context, claudeContextWindow, claudeMaxOutputTokens }) {
  if (runtimeName === "claudecode") {
    const configuredWindow = Number(claudeContextWindow);
    if (!Number.isFinite(configuredWindow) || configuredWindow <= 0) {
      return "📦 context: set CYBERBOSS_CLAUDE_CONTEXT_WINDOW";
    }
    const reservedOutputTokens = Math.max(0, Number(claudeMaxOutputTokens) || 0);
    const availableMessageWindow = configuredWindow - reservedOutputTokens;
    if (availableMessageWindow <= 0) {
      return "📦 context: reduce CLAUDE_CODE_MAX_OUTPUT_TOKENS";
    }
    if (!context || !Number.isFinite(Number(context.currentTokens))) {
      return "📦 context: unavailable";
    }
    const summary = formatContextUsage(Number(context.currentTokens), availableMessageWindow);
    if (reservedOutputTokens > 0) {
      return `📦 context: approx ${summary} | reserve ${formatCompactNumber(reservedOutputTokens)}`;
    }
    return `📦 context: approx ${summary}`;
  }
  if (!context) {
    return "📦 context: unavailable";
  }
  const currentTokens = Number(context.currentTokens);
  const contextWindow = Number(context.contextWindow);
  if (!Number.isFinite(currentTokens) || !Number.isFinite(contextWindow) || contextWindow <= 0) {
    return "📦 context: unavailable";
  }
  return `📦 context: ${formatContextUsage(currentTokens, contextWindow)}`;
}

function formatContextUsage(currentTokens, contextWindow) {
  const safeCurrent = Math.max(0, Number(currentTokens) || 0);
  const safeWindow = Math.max(1, Number(contextWindow) || 1);
  const clampedCurrent = Math.min(safeCurrent, safeWindow);
  const leftPercent = Math.max(0, Math.min(100, Math.round(((safeWindow - clampedCurrent) / safeWindow) * 100)));
  return `${formatCompactNumber(clampedCurrent)}/${formatCompactNumber(safeWindow)} | ${leftPercent}% left`;
}

function buildLocationMovementSystemText(event) {
  const distanceText = `${formatCompactNumber(event?.distanceMeters || 0)}m`;
  const fromLabel = normalizeText(event?.fromAddress) || formatLatLng(event?.fromCenterLat, event?.fromCenterLng);
  const toLabel = normalizeText(event?.toAddress) || formatLatLng(event?.toCenterLat, event?.toCenterLng);
  const movedAt = normalizeText(event?.movedAt) || new Date().toISOString();
  return [
    "System context: the user's location appears to have changed significantly.",
    `Distance: about ${distanceText}.`,
    fromLabel ? `From: ${fromLabel}` : "",
    toLabel ? `To: ${toLabel}` : "",
    `Observed at: ${movedAt}.`,
  ].filter(Boolean).join("\n");
}

function buildLocationTriggerSystemText(trigger) {
  switch (normalizeText(trigger)) {
    case "arrive_home":
      return "User arrives home.";
    case "leave_home":
      return "User leaves home.";
    default:
      return "";
  }
}

function formatLatLng(latitude, longitude) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return "";
  }
  return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}
function createShutdownController(onStop) {
  let stopped = false;
  let stoppingPromise = null;

  const stop = async () => {
    if (stopped) {
      return stoppingPromise;
    }
    stopped = true;
    stoppingPromise = Promise.resolve().then(onStop);
    return stoppingPromise;
  };

  const handleSignal = () => {
    stop().finally(() => {
      process.exit(0);
    });
  };

  process.on("SIGINT", handleSignal);
  process.on("SIGTERM", handleSignal);

  return {
    get stopped() {
      return stopped;
    },
    dispose() {
      process.off("SIGINT", handleSignal);
      process.off("SIGTERM", handleSignal);
    },
  };
}

function assertWeixinUpdateResponse(response) {
  const ret = normalizeErrorCode(response?.ret);
  const errcode = normalizeErrorCode(response?.errcode);
  if ((ret !== 0 && ret !== null) || (errcode !== 0 && errcode !== null)) {
    const error = new Error(
      `weixin getUpdates ret=${ret ?? ""} errcode=${errcode ?? ""} errmsg=${normalizeText(response?.errmsg) || ""}`
    );
    error.ret = ret;
    error.errcode = errcode;
    throw error;
  }
}

// 主人的当地时间。服务器在 UTC 上跑，但面板是给人看的，人看的是自己表上的时间。
// 时区可以用 CB_OWNER_TIMEZONE 改；默认 Asia/Shanghai，和主动打招呼的静默时段
// 用的是同一个时区，两边必须一致，否则「23 点静默」会在两个不同的时刻生效。
const OWNER_TIMEZONE = process.env.CB_OWNER_TIMEZONE || "Asia/Shanghai";

// 发这两个字就给自己那一页的链接。主人的原话：「减少关键词输入」。
// 「我的主页」「首页」「我的网站」也认——同一件事不该因为多打两个字就失灵。
const PERSONAL_SITE_KEYWORD = /^(我的)?(主页|首页|个人主页|个人网站|我的网站)[?？。！!]?$/;

// 体检多久跑一次。十分钟：够快到主人不会先于它发现问题，又不至于把日志刷满。
const HEALTH_CHECK_INTERVAL_MS = 10 * 60_000;

// 发这两个字当场查一次。告警消息里承诺过这一句，必须兑现。
const HEALTH_KEYWORD = /^(体检|自检|你还好吗|系统状态|健康检查)[?？。！!]?$/;

function formatOwnerLocalTime(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: OWNER_TIMEZONE,
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: false,
    }).format(date).replace(/\//g, "-");
  } catch {
    return date.toISOString().slice(5, 19).replace("T", " ");
  }
}

function isSessionExpiredError(error) {
  const ret = normalizeErrorCode(error?.ret);
  const errcode = normalizeErrorCode(error?.errcode);
  return ret === SESSION_EXPIRED_ERRCODE
    || errcode === SESSION_EXPIRED_ERRCODE
    || String(error?.message || "").includes("session expired")
    || String(error?.message || "").includes("session invalidated");
}

function normalizeErrorCode(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatErrorMessage(error) {
  const raw = error instanceof Error ? error.message : String(error || "unknown error");
  if (isSessionExpiredError(error)) {
    return "The WeChat session has expired. Run `npm run login` again.";
  }
  return raw;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 一条收到的附件在库里长什么样。
//
// 只存元数据，字节留在磁盘：把图片本身塞进库会让 GitHub 全量同步变得不可用。
// 但元数据进了库就意味着它跟着那两条同步走——主人要的「全部都保存」在这里才
// 真正成立，落盘而不进库的话，换台机器恢复出来只有一堆无主的文件。
// 字段名照 persistSingleAttachment 真正返回的那些写，不是照想当然的那些。
// 第一版我写了 path / sha256 / bytes 三个——一个都不存在（真名是 relativePath /
// absolutePath / sizeBytes，而 sha256 压根没有）。猜错的后果不是报错，是每条都
// 存成空值，然后没人发现。
function buildMediaNote(item) {
  return JSON.stringify({
    // 存相对路径：绝对路径换台机器恢复出来就是错的，而这张表是要跟着
    // GitHub 全量库和 Cloudflare 冷库走的。
    relativePath: String(item?.relativePath || ""),
    contentType: String(item?.contentType || ""),
    kind: String(item?.kind || ""),
    isImage: Boolean(item?.isImage),
    sizeBytes: Number(item?.sizeBytes || 0) || 0,
    // 微信那边原本的文件名。落盘时会被改名去重，主人找东西时认得的是这个。
    sourceFileName: String(item?.sourceFileName || ""),
  });
}

// 「这个人占不占得到前 N 个席位」的唯一入口。
//
// 收成一个函数而不是三处各写一遍 typeof 判断：这个答案决定要不要把主人的
// Codex 交给对方，三处里漏掉一处的后果不对称——多挡一个人只是他少用一次，
// 多放一个人是把主人的模型给了不该给的人。
//
// 判不出来一律当「没席位」。测试里的桩对象常常没有这个方法，而那种时候正确的
// 答案是不放行，不是崩掉、也不是默认放行。
// 访客的主动问候，给模型的那段指令。
//
// 必须短。这不是风格偏好：微信的 context_token 只允许有限次回复，长文被切成
// 多片之后片数一超，整条就发不出去（WEIXIN_PROVIDER_ERROR）。主人那条路一直
// 是短的，因为 buildSystemInboundText 里写着 one short natural WeChat message；
// 访客这条路以前什么都没写，模型就按聊天正常发挥，写出 500 多字。
function buildGuestCheckinPrompt() {
  return [
    "（系统内部触发，不是对方发来的消息。）",
    "现在主动找他说一句话，就像想起他随口问一句。",
    "只说一句，最多 30 字。不要开场白，不要解释你在做什么，不要提到「系统」或「触发」。",
    "如果实在没什么可说的，就回一个字：略",
  ].join("\n");
}

function hasOwnerSeat(app, userId) {
  if (!app || typeof app.ownerSeatAvailableFor !== "function") {
    return false;
  }
  const normalized = String(userId || "").trim();
  if (!normalized) {
    return false;
  }
  try {
    return Boolean(app.ownerSeatAvailableFor(normalized));
  } catch {
    return false;
  }
}

module.exports = { CyberbossApp };

function parseChannelCommand(text) {
  const normalized = typeof text === "string" ? text.trim() : "";
  if (!normalized.startsWith("/")) {
    return null;
  }
  const [rawName, ...rest] = normalized.slice(1).split(/\s+/);
  const name = normalizeCommandName(rawName);
  if (!name) {
    return null;
  }
  return {
    name,
    args: rest.join(" ").trim(),
  };
}

function normalizeCommandName(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

const WINDOWS_DRIVE_PATH_RE = /^[A-Za-z]:\//;
const WINDOWS_DRIVE_ROOT_RE = /^[A-Za-z]:\/$/;
const WINDOWS_UNC_PREFIX_RE = /^\/\/\?\//;

function normalizeWorkspacePath(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "";
  }

  const fromFileUri = extractPathFromFileUri(normalized);
  const rawPath = fromFileUri || normalized;
  const withForwardSlashes = rawPath.replace(/\\/g, "/").replace(WINDOWS_UNC_PREFIX_RE, "");
  const normalizedDrivePrefix = /^\/[A-Za-z]:\//.test(withForwardSlashes)
    ? withForwardSlashes.slice(1)
    : withForwardSlashes;

  if (WINDOWS_DRIVE_ROOT_RE.test(normalizedDrivePrefix)) {
    return normalizedDrivePrefix;
  }
  if (WINDOWS_DRIVE_PATH_RE.test(normalizedDrivePrefix)) {
    return normalizedDrivePrefix.replace(/\/+$/g, "");
  }
  return normalizedDrivePrefix.replace(/\/+$/g, "");
}

function isAbsoluteWorkspacePath(value) {
  const normalized = normalizeWorkspacePath(value);
  if (!normalized) {
    return false;
  }
  if (WINDOWS_DRIVE_PATH_RE.test(normalized)) {
    return true;
  }
  return path.posix.isAbsolute(normalized);
}

function extractPathFromFileUri(value) {
  const input = String(value || "").trim();
  if (!/^file:\/\//i.test(input)) {
    return "";
  }

  try {
    const parsed = new URL(input);
    if (parsed.protocol !== "file:") {
      return "";
    }
    const pathname = decodeURIComponent(parsed.pathname || "");
    const withHost = parsed.host && parsed.host !== "localhost"
      ? `//${parsed.host}${pathname}`
      : pathname;
    return withHost;
  } catch {
    return "";
  }
}

function normalizeCommandArgument(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeThreadId(value) {
  const normalized = normalizeCommandArgument(value);
  if (!normalized) {
    return "";
  }
  return normalized.replace(/\s+/g, "");
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeIsoTime(value) {
  const normalized = normalizeText(value);
  if (!normalized) {
    return "";
  }
  const parsed = Date.parse(normalized);
  if (!Number.isFinite(parsed)) {
    return "";
  }
  return new Date(parsed).toISOString();
}

function matchesBuiltInCommandPrefix(commandTokens) {
  const normalized = normalizeCommandTokensForMatching(commandTokens);
  if (!normalized.length) {
    return false;
  }

  if (normalized[0] === "view_image") {
    return true;
  }

   if (normalized[0] === "mcp_tool" && normalized[1] === "cyberboss_tools") {
    return true;
  }

  return false;
}

function normalizeCommandTokensForMatching(commandTokens) {
  return canonicalizeCommandTokens(commandTokens);
}

function buildApprovalPromptText(approval) {
  if (approval?.kind === "mcp_elicitation") {
    return buildElicitationApprovalPromptText(approval);
  }
  const reasonText = normalizeText(approval?.reason);
  const commandText = normalizeText(approval?.command);
  const toolName = extractToolNameFromReason(reasonText) || "";
  const commandLines = commandText ? commandText.split("\n") : [];
  const firstCommandLine = normalizeText(commandLines[0]);
  const restCommandLines = commandLines.slice(1);
  const shouldShowReason = reasonText && normalizeText(reasonText) !== normalizeText(`Tool: ${firstCommandLine}`);

  const out = [];
  out.push(`🔐 【Approval】${toolName || "Tool request"}`);

  if (shouldShowReason) {
    out.push(`📋 ${reasonText}`);
  }

  if (commandText) {
    if (firstCommandLine) {
      out.push(`⌨️ ${firstCommandLine}`);
    }
    if (restCommandLines.length) {
      out.push(restCommandLines.map((line) => `  ${line}`).join("\n"));
    }
  }

  if (!reasonText && !commandText) {
    out.push("❓ (unknown)");
  }

  out.push("━━━━━━━━━━━━━");
  out.push("💬 Reply with:");
  out.push("👉 /yes    allow once");
  out.push("👉 /always auto-allow");
  out.push("👉 /no     deny");

  return out.join("\n");
}

function extractToolNameFromReason(reason) {
  const normalized = normalizeText(reason);
  if (!normalized) return "";
  if (normalized.toLowerCase().startsWith("tool:")) {
    return normalized.slice(5).trim();
  }
  return normalized;
}

function buildApprovalPromptSignature(approval) {
  const reasonText = normalizeText(approval?.reason);
  const commandText = normalizeText(approval?.command);
  const commandTokens = Array.isArray(approval?.commandTokens)
    ? approval.commandTokens.map((token) => normalizeCommandArgument(token)).filter(Boolean)
    : [];
  return JSON.stringify({
    kind: normalizeText(approval?.kind),
    reason: reasonText,
    command: commandText,
    commandTokens,
    responseTemplate: approval?.responseTemplate || null,
  });
}

function buildApprovalResponsePayload(approval, commandName) {
  const requestId = approval?.requestId;
  if (requestId == null || String(requestId).trim() === "") {
    return null;
  }
  if (approval?.kind === "mcp_tool_call" || approval?.kind === "mcp_elicitation") {
    const responseByCommand = approval?.responseTemplate?.responseByCommand;
    const effectiveCommandName = commandName === "always" ? "yes" : commandName;
    const result = responseByCommand && typeof responseByCommand === "object"
      ? (responseByCommand[commandName] || responseByCommand[effectiveCommandName])
      : null;
    if (!result || typeof result !== "object") {
      return null;
    }
    return { requestId, result };
  }
  const decision = commandName === "no" ? "decline" : "accept";
  return { requestId, decision };
}

function buildApprovalResponseText(approval, commandName, approvalResponse) {
  if (approval?.kind === "mcp_tool_call" || approval?.kind === "mcp_elicitation") {
    if (commandName === "always" && isApprovalAcceptResponse(approvalResponse)) {
      return "💡 Auto-approve enabled for this MCP tool in the current workspace.";
    }
    if (commandName === "yes") {
      return "✅ This request has been approved.";
    }
    return "❌ This request has been cancelled.";
  }
  return commandName === "always"
    ? "💡 Auto-approve enabled for this command prefix in the current workspace."
    : (commandName === "yes" ? "✅ This request has been approved." : "❌ This request has been denied.");
}

function isApprovalAcceptResponse(approvalResponse) {
  if (!approvalResponse || typeof approvalResponse !== "object") {
    return false;
  }
  if (approvalResponse.decision === "accept") {
    return true;
  }
  return normalizeText(approvalResponse.result?.action) === "accept";
}

function buildElicitationApprovalPromptText(approval) {
  const elicitation = approval?.elicitation || {};
  const messageText = normalizeText(elicitation?.message);
  const commandText = normalizeText(approval?.command);
  const approvalKind = normalizeText(elicitation?.approvalKind);
  const out = [];
  out.push(`🔐 【Approval】${normalizeText(approval?.reason) || "MCP request"}`);
  if (messageText) {
    out.push(`📋 ${messageText.split("\n")[0]}`);
  }
  if (commandText) {
    const commandLines = commandText.split("\n").map((line) => normalizeText(line)).filter(Boolean);
    if (commandLines.length) {
      out.push(`⌨️ ${commandLines[0]}`);
      if (commandLines.length > 1) {
        out.push(commandLines.slice(1).map((line) => `  ${line}`).join("\n"));
      }
    }
  }

  const toolDescription = normalizeText(elicitation?.toolDescription);
  if (toolDescription && approvalKind === "mcp_tool_call") {
    out.push("━━━━━━━━━━━━━");
    out.push(`🧾 ${toolDescription}`);
  }

  const supportedCommands = new Set(
    Array.isArray(approval?.responseTemplate?.supportedCommands)
      ? approval.responseTemplate.supportedCommands
      : []
  );
  out.push("━━━━━━━━━━━━━");
  out.push("💬 Reply with:");
  if (supportedCommands.has("yes")) {
    out.push("👉 /yes    allow once");
  }
  if (supportedCommands.has("always") || (supportedCommands.has("yes") && approval?.kind === "mcp_tool_call")) {
    out.push("👉 /always auto-allow");
  }
  if (supportedCommands.has("no")) {
    out.push("👉 /no     cancel this request");
  }
  if (!supportedCommands.size) {
    out.push("⚠️ This Codex MCP request cannot be answered from WeChat yet.");
  }

  return out.join("\n");
}

function buildReminderSystemTrigger(reminder, config = {}) {
  const reminderText = String(reminder?.text || "").trim();
  const userName = String(config?.userName || "").trim() || "the user";
  return `Due reminder for ${userName}: ${reminderText}`;
}

function buildScopeKey(bindingKey, workspaceRoot) {
  const normalizedBindingKey = normalizeText(bindingKey);
  const normalizedWorkspaceRoot = normalizeText(workspaceRoot);
  if (!normalizedBindingKey || !normalizedWorkspaceRoot) {
    return "";
  }
  return `${normalizedBindingKey}::${normalizedWorkspaceRoot}`;
}

function isAutoApprovedStateDirOperation(approval, config = {}) {
  const stateDir = normalizeText(config?.stateDir);
  if (!stateDir) {
    return false;
  }

  const filePaths = extractApprovalFilePaths(approval);
  if (!filePaths.length) {
    return false;
  }

  return filePaths.every((filePath) => isPathWithinRoot(filePath, stateDir));
}

function sortInboundUpdateMessages(messages) {
  return Array.isArray(messages)
    ? messages.slice().sort(compareRawInboundUpdateMessages)
    : [];
}

function compareRawInboundUpdateMessages(left, right) {
  const leftTime = resolveRawInboundMessageTimeMs(left);
  const rightTime = resolveRawInboundMessageTimeMs(right);
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  const leftMessageId = parseMessageIdForOrdering(left?.message_id);
  const rightMessageId = parseMessageIdForOrdering(right?.message_id);
  if (leftMessageId !== rightMessageId) {
    return leftMessageId - rightMessageId;
  }

  const leftSeq = parseNumericOrderValue(left?.seq);
  const rightSeq = parseNumericOrderValue(right?.seq);
  if (leftSeq !== rightSeq) {
    return leftSeq - rightSeq;
  }

  return String(left?.client_id || "").localeCompare(String(right?.client_id || ""));
}

function resolveRawInboundMessageTimeMs(message) {
  const createdAtMs = parseNumericOrderValue(message?.create_time_ms);
  if (createdAtMs > 0) {
    return createdAtMs;
  }
  const createdAtSeconds = parseNumericOrderValue(message?.create_time);
  return createdAtSeconds > 0 ? createdAtSeconds * 1000 : 0;
}

function comparePendingInboundMessages(left, right) {
  const leftTime = Date.parse(String(left?.receivedAt || "")) || 0;
  const rightTime = Date.parse(String(right?.receivedAt || "")) || 0;
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  const leftMessageId = parseMessageIdForOrdering(left?.messageId);
  const rightMessageId = parseMessageIdForOrdering(right?.messageId);
  if (leftMessageId !== rightMessageId) {
    return leftMessageId - rightMessageId;
  }

  return String(left?.text || "").localeCompare(String(right?.text || ""));
}

function parseMessageIdForOrdering(value) {
  const numeric = parseNumericOrderValue(value);
  return numeric > 0 ? numeric : Number.MAX_SAFE_INTEGER;
}

function parseNumericOrderValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

const DEFERRED_REPLY_NOTICE = "由于微信 context_token 的限制，上轮对话里有一部分内容当时没能送达；这次用户再次发来消息、context_token 刷新后，先把遗留内容补上。如果这种情况反复出现，可发送 /chunk <数字>（例如 /chunk 50）调大最小合并字符数，减少消息分片。";
const DEFERRED_PLAIN_REPLY_HEADER = "===== 上轮对话遗留内容 =====";
const DEFERRED_SYSTEM_REPLY_HEADER = "===== 期间模型主动联系 =====";

function formatDeferredSystemReplyText(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return DEFERRED_REPLY_NOTICE;
  }
  if (normalized.startsWith(DEFERRED_REPLY_NOTICE)) {
    return normalized;
  }
  return `${DEFERRED_REPLY_NOTICE}\n\n${normalized}`;
}

function formatDeferredSystemReplyBatch(replies) {
  const grouped = groupDeferredReplies(replies);
  if (!grouped.plain.length && !grouped.system.length) {
    return DEFERRED_REPLY_NOTICE;
  }
  const parts = [
    DEFERRED_REPLY_NOTICE,
  ];
  if (grouped.plain.length) {
    parts.push("", DEFERRED_PLAIN_REPLY_HEADER, grouped.plain.join("\n\n"));
  }
  if (grouped.system.length) {
    parts.push("", DEFERRED_SYSTEM_REPLY_HEADER, grouped.system.join("\n\n"));
  }
  return parts.join("\n");
}

function groupDeferredReplies(replies) {
  const grouped = { plain: [], system: [] };
  for (const reply of Array.isArray(replies) ? replies : []) {
    const normalizedText = String(reply?.text || "").trim();
    if (!normalizedText) {
      continue;
    }
    if (reply?.kind === "system_reply") {
      grouped.system.push(normalizedText);
      continue;
    }
    grouped.plain.push(normalizedText);
  }
  return grouped;
}

function formatWechatLocalTime(receivedAt) {
  const value = typeof receivedAt === "string" ? receivedAt.trim() : "";
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed).replace(/\//g, "-");
}

function stringifyRpcId(value) {
  if (value == null) {
    return "";
  }
  return String(value).trim();
}

function hasRpcId(value) {
  return stringifyRpcId(value) !== "";
}
