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
const { RuntimeSpoolDatabase } = require("../services/db/database-adapter");
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
const { UserTurnRuntime } = require("./user-turn-runtime");
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
const MAX_INBOUND_STICKER_IMAGE_BATCH = 10;
const INBOUND_IMAGE_BATCH_IDLE_MS = 1_500;

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
    });
    this.pendingOperationByRunKey = new Map();
    this.runtimeEventChain = Promise.resolve();
    this.runtimeSpoolDatabase = null;
    this.durableInboxCoordinator = null;
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
      this.personaStore = new PersonaStore({ database: this.runtimeSpoolDatabase });
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
        });
        this.userCompanionTurn = new UserCompanionTurn({
          database: this.runtimeSpoolDatabase.database,
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
          // 前 N 个开通的人用主人的额度；第 N+1 个开始必须自己填密钥。
          ownerQuota: { resolve: (userId) => this.resolveOwnerQuotaFor(userId) },
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
      this.durableInboxCoordinator = new DurableInboxCoordinator({
        channelAdapter: this.channelAdapter,
        database: this.runtimeSpoolDatabase,
        config: this.config,
        // 在建 job 之前分流。非主人的三条路（入门回复、普通用户确定性口令、
        // 席位已满的拒绝）到了调度阶段就没有出口了——JobScheduler 要求
        // dispatchRuntime 返回真实的 threadId/turnId，等于强制走一次模型。
        admissionFilter: (normalized) => this.admissionHandledBeforeJob(normalized),
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
        onAccepted: ({ normalized }) => {
          try {
            this.channelAdapter.rememberContextToken?.(
              normalized.senderId,
              normalized.contextToken,
            );
          } catch {
            // 记不住不该让这条消息进不来；最坏结果是主动消息暂时发不出去。
          }
        },
      });
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
    console.log(`[cyberboss] account=${account.accountId}`);
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
            this.flushDueReminders(account),
            this.flushPendingInboundMessages(),
            this.flushPendingSystemMessages(),
            this.flushPendingTimelineScreenshots(account),
          ]);
          if (this.durableInboxCoordinator) {
            const durable = await this.durableInboxCoordinator.pollOnce({
              timeoutMs: this.resolveLongPollTimeoutMs(),
            });
            this.jobScheduler?.notePollSuccess();
            consecutiveFailures = 0;
            if (durable.acceptedCount || durable.rejectedCount) {
              console.log(
                `[cyberboss] durable batch queued accepted=${durable.acceptedCount} rejected=${durable.rejectedCount}`,
              );
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
            this.flushDueReminders(account),
            this.flushPendingInboundMessages(),
            this.flushPendingSystemMessages(),
            this.flushPendingTimelineScreenshots(account),
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
      adminPersonaRead: () => this.readDashboardPersona(),
      adminPersonaWrite: (input) => this.writeDashboardPersona(input),
      publicEntry: () => this.buildPublicEntry(),
      adminSessionIssue: (input) => this.issueAdminSession(input),
      adminSessionVerify: (cookieHeader) => this.adminSessionValid(cookieHeader),
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

  // 后台页面上那段"最近发生了什么"。只留人话，且不含任何消息内容。
  recentLog() {
    return (this.dashboardLog || []).slice(-40);
  }

  noteForDashboard(text) {
    if (!this.dashboardLog) {
      this.dashboardLog = [];
    }
    this.dashboardLog.push(`${new Date().toISOString().slice(5, 19).replace("T", " ")}  ${text}`);
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

  // 公开页要显示的东西。这一页**任何人都能打开**，所以它只含两样：一张由主人
  // 配的入口地址渲染出来的二维码，和一句怎么用。不含任何用量、人数、状态——
  // 那些都是运营信息，公开页上一个字都不该有。
  buildPublicEntry() {
    let access = null;
    try {
      access = this.personaStore ? this.personaStore.read().access : null;
    } catch {
      access = null;
    }
    const bound = (() => {
      try {
        return this.userAdmission ? this.userAdmission.ownerChannelBound() : false;
      } catch {
        return false;
      }
    })();
    if (!bound) {
      return Object.freeze({
        ok: true, ready: false, status: "pending_activation",
        message: "这个机器人还没准备好，请稍后再来。",
      });
    }
    if (!access?.entryUrl) {
      return Object.freeze({
        ok: true, ready: false, status: "pending_entry_qr",
        message: "入口二维码还没配好，请稍后再来。",
      });
    }
    let qrDataUri = "";
    try {
      qrDataUri = svgDataUri(renderQrSvg(access.entryUrl, { ariaLabel: "加机器人的二维码" }));
    } catch {
      return Object.freeze({
        ok: true, ready: false, status: "pending_entry_qr",
        message: "入口二维码还没配好，请稍后再来。",
      });
    }
    const seatsLeft = (() => {
      try {
        const used = this.userAdmission?.users?.countActiveOrdinaryUsers?.();
        const limit = this.resolveSeatLimit();
        return Number.isFinite(used) && Number.isInteger(limit) ? Math.max(0, limit - used) : null;
      } catch {
        return null;
      }
    })();
    return Object.freeze({
      ok: true,
      ready: true,
      status: "ready",
      qrDataUri,
      open: access.mode === "open",
      // 只说"满了没有"，不说还剩几个、更不说有多少人——公开页上人数是运营信息。
      full: seatsLeft === 0,
      message: seatsLeft === 0
        ? "名额暂时满了。"
        : (access.mode === "open"
          ? "用微信扫这个码加它，然后随便说句话就能用。"
          : "用微信扫这个码加它，再把主人给你的邀请码发过去。"),
    });
  }

  // ── 语气面板 ───────────────────────────────────────────────

  readDashboardPersona() {
    const persona = this.personaStore ? this.personaStore.read() : null;
    return Object.freeze({
      ok: true,
      persona: persona || {},
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
      preview: this.currentPersonaInstruction(),
    });
  }

  writeDashboardPersona(input) {
    if (!this.personaStore) {
      return Object.freeze({ ok: false, code: "PERSONA_STORE_UNAVAILABLE" });
    }
    try {
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
  noteDirectReply(userId, text) {
    const persisted = this.noteBotInitiated({
      kind: "onboarding", senderId: userId, text, delivered: true,
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
        if (token && this.channelAdapter.rememberContextToken(senderId, token)) {
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
      const roles = this.runtimeSpoolDatabase.listUserRolesForOwner();
      for (const message of this.runtimeSpoolDatabase.listRecentInboundForOwner({ limit: 200 })) {
        const sender = message.payload?.senderId || "";
        if (!sender) {
          continue;
        }
        if (message.userId === ownerUserId || roles.get(message.userId) === "owner") {
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
  ownerProviderCredential() {
    if (this.ownerCredentialCache !== undefined) {
      return this.ownerCredentialCache;
    }
    let apiKey = "";
    try {
      // 环境变量优先，其次 systemd credential。密钥只在内存里，不落日志、
      // 不落配置、不进任何一条聊天记录。
      apiKey = loadRuntimeTextSecret({
        envName: "DEEPSEEK_API_KEY",
        credentialName: "deepseek-api-key",
      });
    } catch {
      apiKey = "";
    }
    this.ownerCredentialCache = apiKey
      ? Object.freeze({ providerId: "deepseek", model: "deepseek-chat", apiKey })
      : null;
    return this.ownerCredentialCache;
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
    });
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
const { loadRuntimeTextSecret } = require("../v8-prebuilt/security/runtime-text-secret");
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
    // owner 与 user 两条路都要真正的 turn，交给 job 队列。
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
    if (decision.route !== "owner") {
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
      await this.runUserModelTurn(normalized, decision.userContext);
      return null;
    }
    if (decision.ownerClaimed) {
      // 第一条消息就把主人认下来了，告诉他这件事已经发生，并给出下一步。
      await this.sendAdmissionReply(normalized, OWNER_CLAIMED_NOTICE);
      this.rememberOwnerSender(normalized.senderId);
    }
    return decision;
  }

  async sendAdmissionReply(normalized, text) {
    if (!text) {
      return;
    }
    // 这条不走 outbox，数据库里查不到，所以在这里留一份给后台「对话」栏。
    this.noteDirectReply(normalized.senderId, text);
    await this.channelAdapter.sendText({
      userId: normalized.senderId,
      text,
      contextToken: normalized.contextToken,
    }).catch(() => {});
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

  deferSystemReply({ threadId = "", userId = "", text = "", error = null, kind = "plain_reply" }) {
    return this.deferredSystemReplyQueue.enqueue({
      id: `${normalizeCommandArgument(threadId) || "system"}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
      accountId: this.activeAccountId || this.channelAdapter.resolveAccount().accountId,
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
    if (this.userAdmission && prepared?.provider !== "system") {
      const capability = this.runtimeAdapter.describe().id === "claudecode"
        ? "claudecode.turn"
        : "codex.turn";
      if (!turnContext || !turnContext.may(capability)) {
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
        // 每一轮现读一次，不缓存：主人在后台改完语气，下一句话就该变。
        personaInstruction: this.currentPersonaInstruction(),
      }),
      attachments: Array.isArray(visionContext.runtimeAttachments) ? visionContext.runtimeAttachments : [],
      visionContext,
    };
  }

  // 语气块。读不出来就返回空串——语气不是必需品，不能因为它发不出消息。
  currentPersonaInstruction() {
    if (!this.personaStore) {
      return "";
    }
    try {
      return renderPersonaInstruction(this.personaStore.read());
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
        const dispatched = await this.dispatchSystemMessage(message);
        if (!dispatched) {
          this.systemMessageDispatcher.requeue(message);
        }
      } catch {
        this.systemMessageDispatcher?.requeue(message);
      }
    }
  }

  async flushPendingTimelineScreenshots(account) {
    const pendingJobs = this.timelineScreenshotQueue.drainForAccount(account.accountId);
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
    if (this.activeAccountId && this.timelineScreenshotQueue.hasPendingForAccount(this.activeAccountId)) {
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

  async flushDueReminders(account) {
    const dueReminders = this.reminderQueue
      .listDue(Date.now())
      .filter((reminder) => reminder.accountId === account.accountId);

    for (const reminder of dueReminders) {
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
