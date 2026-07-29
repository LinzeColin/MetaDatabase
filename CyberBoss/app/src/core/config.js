const os = require("os");
const path = require("path");
const { WorkspaceRegistry } = require("./workspace-registry");

function readConfig() {
  const argv = process.argv.slice(2);
  const mode = argv[0] || "";
  const stateDir = process.env.CYBERBOSS_STATE_DIR || path.join(os.homedir(), ".cyberboss");
  const durableInboxOverride = readOptionalBoolEnv("CB_DURABLE_INBOX");
  const durableInbox = durableInboxOverride === undefined
    ? true
    : durableInboxOverride;
  const baselineStagingAllowed =
    readBoolEnv("CB_ALLOW_BASELINE_STAGING")
    && readTextEnv("NODE_ENV").toLowerCase() !== "production";
  if (!durableInbox && !baselineStagingAllowed) {
    throw new Error("CB_DURABLE_INBOX=false is allowed only in explicit non-production staging");
  }
  const jobSchedulerOverride = readOptionalBoolEnv("CB_JOB_SCHEDULER");
  const jobScheduler = durableInbox && (
    jobSchedulerOverride === undefined ? true : jobSchedulerOverride
  );
  if (durableInbox && !jobScheduler && !baselineStagingAllowed) {
    throw new Error("CB_JOB_SCHEDULER=false is allowed only in explicit non-production staging");
  }
  const durableOutboxOverride = readOptionalBoolEnv("CB_DURABLE_OUTBOX");
  const durableOutbox = jobScheduler && (
    durableOutboxOverride === undefined ? true : durableOutboxOverride
  );
  if (jobScheduler && !durableOutbox && !baselineStagingAllowed) {
    throw new Error("CB_DURABLE_OUTBOX=false is allowed only in explicit non-production staging");
  }
  const canonicalSyncOverride = readOptionalBoolEnv(
    "CB_PRIVATE_DB_CANONICAL_SYNC",
  );
  const canonicalSync = durableOutbox && (
    canonicalSyncOverride === undefined ? true : canonicalSyncOverride
  );
  if (durableOutbox && !canonicalSync && !baselineStagingAllowed) {
    throw new Error(
      "CB_PRIVATE_DB_CANONICAL_SYNC=false is allowed only in explicit non-production staging",
    );
  }
  const canonicalLegacyFlushOverride = readOptionalBoolEnv(
    "CB_CANONICAL_FLUSH_ON_TERMINAL",
  );
  const canonicalMaterialFlush = canonicalLegacyFlushOverride !== false;
  const canonicalOrdinarySyncSchedule = readTextEnv(
    "CB_CANONICAL_ORDINARY_SYNC_SCHEDULE",
  ) || "daily";
  const canonicalOrdinarySyncOnCalendar = readTextEnv(
    "CB_CANONICAL_ORDINARY_SYNC_ON_CALENDAR",
  ) || "*-*-* 03:20:00 UTC";
  const canonicalMaterialEventTypes = readListEnv(
    "CB_CANONICAL_MATERIAL_EVENT_TYPES",
  );
  if (
    !canonicalMaterialFlush ||
    canonicalOrdinarySyncSchedule !== "daily" ||
    canonicalOrdinarySyncOnCalendar !== "*-*-* 03:20:00 UTC" ||
    (
      canonicalMaterialEventTypes.length > 0 &&
      canonicalMaterialEventTypes.slice().sort().join(",") !==
        "incident_declared,recovery_completed,release_completed"
    )
  ) {
    throw new Error("CB_CANONICAL_SYNC_POLICY_INVALID");
  }
  // v0.0.0.8 multi-user admission. It rides on the runtime database, so it can
  // only be on where that database exists; with no database there is no user
  // table, no UserContext and therefore no safe way to admit a second sender.
  const allowedUserIds = readListEnv("CYBERBOSS_ALLOWED_USER_IDS");
  const multiUserOverride = readOptionalBoolEnv("CB_MULTI_USER");
  const multiUser = durableInbox && (
    multiUserOverride === undefined ? true : multiUserOverride
  );
  const registrationMode = readTextEnv("CB_REGISTRATION_MODE") || "invite";
  if (!["invite", "open"].includes(registrationMode)) {
    throw new Error("CB_REGISTRATION_MODE must be invite or open");
  }
  // The Owner senders default to the pre-existing allowlist, so an installation
  // that already names its Owner keeps exactly the behaviour it has today and
  // every other sender becomes an ordinary, isolated user instead of a silent
  // rejection.
  const ownerSenderIds = readListEnv("CB_OWNER_SENDER_IDS").length
    ? readListEnv("CB_OWNER_SENDER_IDS")
    : allowedUserIds;
  // The public https origin the setup page is served from. Absent on a host
  // that has no public endpoint yet; 「设置」 then says so rather than handing
  // out a link that cannot resolve.
  const portalOrigin = readTextEnv("CB_PORTAL_ORIGIN");
  if (portalOrigin && !/^https:\/\/[^/?#]+$/.test(portalOrigin)) {
    throw new Error("CB_PORTAL_ORIGIN must be a bare https origin");
  }

  const workspaceConfigFile = readTextEnv("CYBERBOSS_WORKSPACE_CONFIG")
    || path.join(stateDir, "workspaces.json");
  const workspaceBase = readTextEnv("CYBERBOSS_WORKSPACE_BASE")
    || "/srv/cyberboss-workspaces";
  const workspaceRegistry = new WorkspaceRegistry({
    configPath: workspaceConfigFile,
    workspaceBase,
  });
  const workspaceAlias = readTextEnv("CYBERBOSS_WORKSPACE_ALIAS")
    || workspaceRegistry.defaultAlias;
  const workspace = workspaceRegistry.resolve(workspaceAlias);
  const configuredWorkspaceRoot = readTextEnv("CYBERBOSS_WORKSPACE_ROOT");
  if (configuredWorkspaceRoot) {
    const configured = workspaceRegistry.assertAllowedRoot(configuredWorkspaceRoot);
    if (configured.alias !== workspace.alias) {
      throw new Error("CYBERBOSS_WORKSPACE_ROOT does not match CYBERBOSS_WORKSPACE_ALIAS");
    }
  }

  return {
    mode,
    argv,
    stateDir,
    workspaceId: readTextEnv("CYBERBOSS_WORKSPACE_ID") || "default",
    workspaceAlias: workspace.alias,
    workspaceRoot: workspace.root,
    workspaceBase,
    workspaceConfigFile,
    workspaceRegistry,
    userName: readTextEnv("CYBERBOSS_USER_NAME") || "User",
    userGender: readTextEnv("CYBERBOSS_USER_GENDER") || "female",
    allowedUserIds,
    multiUser,
    registrationMode,
    // 默认 false：扫码进来的人第一句话就能用。告知照发，但不挡路。
    // 要退回「必须先回一句同意并开始」那种两步式，设 CB_REQUIRE_EXPLICIT_CONSENT=true。
    requireExplicitConsent: readTextEnv("CB_REQUIRE_EXPLICIT_CONSENT") === "true",
    ownerSenderIds,
    portalOrigin,
    // 只监听回环地址。公网入口是 Cloudflare Tunnel，本机不开任何入站端口。
    portalHost: readTextEnv("CB_PORTAL_HOST") || "127.0.0.1",
    portalPort: readIntEnv("CB_PORTAL_PORT") || 8787,
    adminToken: readTextEnv("CB_ADMIN_TOKEN"),
    dailyTokenBudget: readIntEnv("CB_DAILY_TOKEN_BUDGET") || 200_000,
    // 云备份的两个目标。缺任何一边，备份就如实报 activation_pending，而不是
    // 只写一份副本还发一张声称有两份的收据。
    r2AccountId: readTextEnv("CB_R2_ACCOUNT_ID"),
    r2Bucket: readTextEnv("CB_R2_BUCKET"),
    r2AccessKeyId: readTextEnv("CB_R2_ACCESS_KEY_ID"),
    r2SecretAccessKey: readTextEnv("CB_R2_SECRET_ACCESS_KEY"),
    ociParUrl: readTextEnv("CB_OCI_PAR_URL"),
    userTurnTimeoutMs: readIntEnv("CB_USER_TURN_TIMEOUT_MS"),
    maxInputBytes: readIntEnv("CYBERBOSS_MAX_INPUT_BYTES")
      || readIntEnv("CB_MAX_INPUT_BYTES")
      || 32 * 1024,
    durableInbox,
    jobScheduler,
    durableOutbox,
    canonicalSync,
    baselineStagingAllowed,
    runtimeDatabasePath: readTextEnv("CB_RUNTIME_DB")
      || path.join(stateDir, "runtime.db"),
    runtimeEncryptionKeyFile: readTextEnv("CB_RUNTIME_ENCRYPTION_KEY_FILE")
      || path.join(stateDir, "credentials", "runtime-encryption.key"),
    runtimeIdentityKeyFile: readTextEnv("CB_RUNTIME_IDENTITY_KEY_FILE")
      || path.join(stateDir, "credentials", "runtime-identity.key"),
    activePayloadTtlHours: readIntEnv("CB_ACTIVE_PAYLOAD_TTL_HOURS") || 24,
    runtimeLeaseMs: readIntEnv("CB_RUNTIME_LEASE_MS") || 30_000,
    controlLeaseMs: readIntEnv("CB_CONTROL_LEASE_MS") || 10_000,
    outboxLeaseMs: readIntEnv("CB_OUTBOX_LEASE_MS") || 10_000,
    outboxMaxAttempts: readIntEnv("CB_OUTBOX_MAX_ATTEMPTS") || 5,
    outboxBaseDelayMs: readIntEnv("CB_OUTBOX_BASE_DELAY_MS") || 1_000,
    outboxMaxDelayMs: readIntEnv("CB_OUTBOX_MAX_DELAY_MS") || 60_000,
    outboxChunkChars: readIntEnv("CB_OUTBOX_CHUNK_CHARS") || 3_600,
    canonicalSpoolRoot: readTextEnv("CB_CANONICAL_SPOOL_ROOT")
      || path.join(stateDir, "canonical-spool"),
    canonicalDeployedCommit: readTextEnv("CB_EXPECTED_RELEASE_ID"),
    canonicalBatchMax: readIntEnv("CB_CANONICAL_BATCH_MAX") || 50,
    canonicalBatchMaxBytes:
      readIntEnv("CB_CANONICAL_BATCH_MAX_BYTES") || 262_144,
    canonicalBatchMaxAgeMs:
      readIntEnv("CB_CANONICAL_BATCH_MAX_AGE_MS") || 60_000,
    canonicalMaterialFlush,
    canonicalOrdinarySyncSchedule,
    canonicalOrdinarySyncOnCalendar,
    canonicalMaterialEventTypes:
      canonicalMaterialEventTypes.length > 0
        ? canonicalMaterialEventTypes.slice().sort()
        : [
            "incident_declared",
            "recovery_completed",
            "release_completed",
          ],
    canonicalMaxEventsPerInvocation:
      readIntEnv("CB_CANONICAL_MAX_EVENTS_PER_INVOCATION") || 2_000,
    canonicalMaxUncompressedBytesPerInvocation:
      readIntEnv("CB_CANONICAL_MAX_UNCOMPRESSED_BYTES_PER_INVOCATION") ||
      10 * 1024 * 1024,
    canonicalMaxAttemptsPerInvocation:
      readIntEnv("CB_CANONICAL_MAX_ATTEMPTS_PER_INVOCATION") || 5,
    canonicalBacklogMaxEvents:
      readIntEnv("CB_CANONICAL_BACKLOG_MAX_EVENTS") || 10_000,
    canonicalBacklogMaxBytes:
      readIntEnv("CB_CANONICAL_BACKLOG_MAX_BYTES") || 64 * 1024 * 1024,
    canonicalMaxLagSeconds:
      readIntEnv("CB_CANONICAL_MAX_LAG_SECONDS") || 900,
    pollStaleMs: readIntEnv("CB_POLL_STALE_MS") || 90_000,
    queueStuckMs: readIntEnv("CB_QUEUE_STUCK_MS") || 5 * 60_000,
    schedulerQueueLimit: readIntEnv("CB_QUEUE_LIMIT") || 20,
    walkingSkeletonTraceFile: readTextEnv("CYBERBOSS_WALKING_SKELETON_TRACE_FILE"),
    channel: readTextEnv("CYBERBOSS_CHANNEL") || "weixin",
    runtime: readTextEnv("CYBERBOSS_RUNTIME") || "codex",
    timelineCommand: readTextEnv("CYBERBOSS_TIMELINE_COMMAND") || "timeline-for-agent",
    accountId: readTextEnv("CYBERBOSS_ACCOUNT_ID"),
    weixinBaseUrl: readTextEnv("CYBERBOSS_WEIXIN_BASE_URL") || "https://ilinkai.weixin.qq.com",
    weixinCdnBaseUrl: readTextEnv("CYBERBOSS_WEIXIN_CDN_BASE_URL") || "https://novac2c.cdn.weixin.qq.com/c2c",
    weixinConfigFile: path.join(stateDir, "weixin-config.json"),
    weixinMinChunkChars: readIntEnv("CYBERBOSS_WEIXIN_MIN_CHUNK_CHARS"),
    weixinQrBotType: readTextEnv("CYBERBOSS_WEIXIN_QR_BOT_TYPE") || "3",
    accountsDir: path.join(stateDir, "accounts"),
    reminderQueueFile: path.join(stateDir, "reminder-queue.json"),
    systemMessageQueueFile: path.join(stateDir, "system-message-queue.json"),
    deferredSystemReplyQueueFile: path.join(stateDir, "deferred-system-replies.json"),
    checkinConfigFile: path.join(stateDir, "checkin-config.json"),
    timelineScreenshotQueueFile: path.join(stateDir, "timeline-screenshot-queue.json"),
    projectToolContextFile: path.join(stateDir, "project-tool-runtime-context.json"),
    // 前 N 个人共用主人这把钥匙时，用哪个模型。
    //
    // 这三样必须能填，不能写死在代码里：它们是外部服务认的**确切字符串**，
    // 猜错一个字母，每一轮都会失败——而且换模型不该需要改代码重新部署。
    // 以前 deepseek 是写死的，「有人反应说是 deepseek」就是这么来的。
    ownerModelOpenAI: String(process.env.CB_OWNER_MODEL_OPENAI || "gpt-5").trim(),
    ownerModelDeepSeek: String(process.env.CB_OWNER_MODEL_DEEPSEEK || "deepseek-chat").trim(),
    // OpenAI 推理档位：low / medium / high。别的 provider 忽略。
    ownerReasoningEffort: ["low", "medium", "high"].includes(
      String(process.env.CB_OWNER_REASONING_EFFORT || "").trim(),
    ) ? String(process.env.CB_OWNER_REASONING_EFFORT).trim() : "",
    weixinInstructionsFile: path.join(stateDir, "weixin-instructions.md"),
    weixinOperationsFile: path.resolve(__dirname, "..", "..", "templates", "weixin-operations.md"),
    stickersDir: path.join(stateDir, "stickers"),
    stickerAssetsDir: path.join(stateDir, "stickers", "assets"),
    stickersIndexFile: path.join(stateDir, "stickers", "index.json"),
    stickerTagsFile: path.join(stateDir, "stickers", "tags.json"),
    stickersTemplateDir: path.resolve(__dirname, "..", "..", "templates", "stickers"),
    stickersTemplateIndexFile: path.resolve(__dirname, "..", "..", "templates", "stickers", "index.json"),
    stickerTagsTemplateFile: path.resolve(__dirname, "..", "..", "templates", "stickers", "tags.json"),
    stickerNormalizeGifScript: path.resolve(__dirname, "..", "..", "scripts", "normalize-sticker-gif.js"),
    diaryDir: path.join(stateDir, "diary"),
    locationStoreFile: path.join(stateDir, "locations.json"),
    locationHost: readTextEnv("CYBERBOSS_LOCATION_HOST") || "0.0.0.0",
    locationPort: readIntEnv("CYBERBOSS_LOCATION_PORT") || 4318,
    locationToken: readTextEnv("CYBERBOSS_LOCATION_TOKEN"),
    locationHistoryLimit: readIntEnv("CYBERBOSS_LOCATION_HISTORY_LIMIT") || 1000,
    locationMovementEventLimit: readIntEnv("CYBERBOSS_LOCATION_MOVEMENT_EVENT_LIMIT"),
    locationBatteryHistoryLimit: readIntEnv("CYBERBOSS_LOCATION_BATTERY_HISTORY_LIMIT"),
    locationKnownPlaces: readKnownPlacesEnv(),
    locationKnownPlaceRadiusMeters: readIntEnv("CYBERBOSS_LOCATION_PLACE_RADIUS_METERS") || 150,
    locationStayMergeRadiusMeters: readIntEnv("CYBERBOSS_LOCATION_STAY_MERGE_RADIUS_METERS") || 100,
    locationStayBreakConfirmRadiusMeters: readIntEnv("CYBERBOSS_LOCATION_STAY_BREAK_RADIUS_METERS") || 200,
    locationStayBreakConfirmSamples: readIntEnv("CYBERBOSS_LOCATION_STAY_BREAK_SAMPLES") || 2,
    locationMajorMoveThresholdMeters: readIntEnv("CYBERBOSS_LOCATION_MAJOR_MOVE_THRESHOLD_METERS") || 1000,
    startWithLocationServer: resolveLocationServerEnabled({
      mode,
      enabled: readOptionalBoolEnv("CYBERBOSS_ENABLE_LOCATION_SERVER"),
    }),
    syncBufferDir: path.join(stateDir, "sync-buffers"),
    codexEndpoint: readTextEnv("CYBERBOSS_CODEX_ENDPOINT"),
    codexCommand: readTextEnv("CYBERBOSS_CODEX_COMMAND"),
    codexModel: readTextEnv("CYBERBOSS_CODEX_MODEL"),
    codexModelProvider: readTextEnv("CYBERBOSS_CODEX_MODEL_PROVIDER"),
    codexNativeImageInput: readOptionalBoolEnv("CYBERBOSS_CODEX_NATIVE_IMAGE_INPUT"),
    visionMode: readTextEnv("CYBERBOSS_VISION_MODE") || "auto",
    visionProvider: readTextEnv("CYBERBOSS_VISION_PROVIDER") || "openai-compatible",
    visionApiBaseUrl: readTextEnv("CYBERBOSS_VISION_API_BASE_URL"),
    visionApiKey: readTextEnv("CYBERBOSS_VISION_API_KEY"),
    visionModel: readTextEnv("CYBERBOSS_VISION_MODEL"),
    visionTimeoutMs: readIntEnv("CYBERBOSS_VISION_TIMEOUT_MS") || 30_000,
    claudeCommand: readTextEnv("CYBERBOSS_CLAUDE_COMMAND") || "claude",
    claudeModel: readTextEnv("CYBERBOSS_CLAUDE_MODEL") || "",
    claudeContextWindow: readIntEnv("CYBERBOSS_CLAUDE_CONTEXT_WINDOW"),
    claudeMaxOutputTokens: readIntEnv("CLAUDE_CODE_MAX_OUTPUT_TOKENS"),
    claudePermissionMode: readTextEnv("CYBERBOSS_CLAUDE_PERMISSION_MODE") || "default",
    claudeDisableVerbose: readBoolEnv("CYBERBOSS_CLAUDE_DISABLE_VERBOSE"),
    claudeExtraArgs: readListEnv("CYBERBOSS_CLAUDE_EXTRA_ARGS"),
    sessionsFile: path.join(stateDir, "sessions.json"),
    startWithCheckin: (mode === "start" && hasArgFlag(argv, "--checkin")) || readBoolEnv("CYBERBOSS_ENABLE_CHECKIN"),
  };
}

function readListEnv(name) {
  return String(process.env[name] || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function readTextEnv(name) {
  const value = process.env[name];
  return typeof value === "string" ? value.trim() : "";
}

function readBoolEnv(name) {
  const value = readTextEnv(name).toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

function readOptionalBoolEnv(name) {
  const value = readTextEnv(name).toLowerCase();
  if (!value) {
    return undefined;
  }
  if (value === "1" || value === "true" || value === "yes" || value === "on") {
    return true;
  }
  if (value === "0" || value === "false" || value === "no" || value === "off") {
    return false;
  }
  return undefined;
}

function readIntEnv(name) {
  const value = readTextEnv(name);
  if (!value) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function readKnownPlacesEnv() {
  const fromJson = parseKnownPlacesJson(readTextEnv("CYBERBOSS_LOCATION_KNOWN_PLACES"));
  const fromCenters = [
    parseKnownPlaceCenter("home", readTextEnv("CYBERBOSS_LOCATION_HOME_CENTER")),
    parseKnownPlaceCenter("work", readTextEnv("CYBERBOSS_LOCATION_WORK_CENTER")),
  ].filter(Boolean);
  return [...fromJson, ...fromCenters];
}

function parseKnownPlacesJson(value) {
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parseKnownPlaceCenter(tag, value) {
  const parts = value.split(",").map((part) => part.trim()).filter(Boolean);
  if (parts.length !== 2) {
    return null;
  }
  const latitude = Number(parts[0]);
  const longitude = Number(parts[1]);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }
  return { tag, latitude, longitude };
}

function hasArgFlag(argv, flag) {
  return Array.isArray(argv) && argv.some((item) => String(item || "").trim() === flag);
}

function resolveLocationServerEnabled({ mode, enabled }) {
  if (mode !== "start") {
    return false;
  }
  if (typeof enabled === "boolean") {
    return enabled;
  }
  return false;
}

module.exports = { readConfig };
