'use strict';
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { SqliteUserRepository } = require('../users/user-repository');
const { RegistrationService } = require('../users/registration-service');
const { WebSessionService } = require('../public-entry/web-session-service');
const { ILinkLoginClient } = require('../public-entry/ilink-login-client');
const { SqliteOwnerActivationStore } = require('../public-entry/owner-activation-store');
const { OwnerWeChatActivationService } = require('../public-entry/owner-wechat-activation-service');
const { SharedEntryService } = require('../public-entry/shared-entry-service');
const { createPublicEntryServer } = require('../public-entry/public-entry-server');
const { SharedBotAccountStore } = require('../weixin/shared-bot-account-store');
const { SqliteIngressStore } = require('../weixin/sqlite-ingress-store');
const { SqliteReplyOutbox } = require('../weixin/sqlite-reply-outbox');
const { DurableReplyDispatcher } = require('../weixin/durable-reply-dispatcher');
const { FirstReplyService } = require('../weixin/first-reply-service');
const { WeixinAccountSupervisor } = require('../weixin/account-supervisor');
const { encryptJson, decryptJson } = require('../weixin/payload-crypto');
const { bindReplyRoute } = require('../channel/reply-route-binding');
const { MvpRuntime } = require('./mvp-runtime');
const { UserMessageRuntime } = require('./user-message-runtime');
const { FiveSeatRegistry } = require('./five-seat-registry');
const { GlobalDailyTokenLedger } = require('./global-daily-token-ledger');
const { SqliteDeepSeekCircuitBreaker } = require('./sqlite-deepseek-circuit-breaker');
const { DeepSeekV4ProRuntime } = require('./deepseek-v4-pro-runtime');
const { SharedDeepSeekController } = require('./shared-deepseek-controller');
const { projectSharedDeepSeekStatus } = require('./shared-deepseek-status');
const { loadRuntimeSecret } = require('../security/runtime-secret');
const { loadRuntimeTextSecret } = require('../security/runtime-text-secret');

function assertOwnerUserId(value) {
  const text = String(value || '').trim();
  if (!/^usr_[A-Za-z0-9_-]{20,}$/.test(text)) throw Object.assign(new Error('CYBERBOSS_OWNER_USER_ID_INVALID'), { code: 'CYBERBOSS_OWNER_USER_ID_INVALID' });
  return text;
}

function createMvpComponents({
  dbPath,
  assetRoot = path.join(__dirname, '../../public'),
  env = process.env,
  fetchImpl = globalThis.fetch,
  onUserMessage = null,
  authorizeOwner = () => false,
  clock = () => Date.now(),
} = {}) {
  if (!dbPath) throw new TypeError('dbPath required');
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;');

  const identityKey = loadRuntimeSecret({ env, envName: 'CYBERBOSS_IDENTITY_KEY', credentialName: 'identity-key' });
  const masterKey = loadRuntimeSecret({ env, envName: 'CYBERBOSS_MASTER_KEY', credentialName: 'master-key' });
  const sessionKey = loadRuntimeSecret({ env, envName: 'CYBERBOSS_SESSION_KEY', credentialName: 'session-key' });
  const payloadKey = loadRuntimeSecret({ env, envName: 'CYBERBOSS_PAYLOAD_KEY', credentialName: 'payload-key' });
  const routeKey = loadRuntimeSecret({ env, envName: 'CYBERBOSS_ROUTE_KEY', credentialName: 'route-key' });
  const deepSeekApiKey = loadRuntimeTextSecret({ env, envName: 'DEEPSEEK_API_KEY', credentialName: 'deepseek-api-key' });
  const ownerUserId = assertOwnerUserId(env.CYBERBOSS_OWNER_USER_ID);
  const nowIso = () => new Date(clock()).toISOString();
  db.prepare(`INSERT INTO users(user_id,role,status,consent_version,consented_at,created_at,updated_at)
    VALUES(?,'owner','active','owner-bootstrap',?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET role='owner',status='active',updated_at=excluded.updated_at`)
    .run(ownerUserId, nowIso(), nowIso(), nowIso());

  const users = new SqliteUserRepository({ db, identityKey, clock: nowIso });
  const seats = new FiveSeatRegistry({ db, clock });
  const registration = new RegistrationService({ userRepository: users, seatRegistry: seats, registrationMode: 'open', policyVersion: env.CYBERBOSS_POLICY_VERSION || 'privacy-v1' });
  const webSessions = new WebSessionService({ db, sessionKey, clock });

  const sharedBotAccounts = new SharedBotAccountStore({ db, masterKey, ownerUserId, clock });
  const activationStore = new SqliteOwnerActivationStore(db);
  const loginClient = new ILinkLoginClient({ baseUrl: env.CYBERBOSS_ILINK_LOGIN_BASE_URL || 'https://ilinkai.weixin.qq.com/', fetchImpl });
  const ownerActivation = new OwnerWeChatActivationService({ client: loginClient, store: activationStore, sharedBotAccounts, clock });
  const entryService = new SharedEntryService({
    entryUrlProvider: () => env.CYBERBOSS_PUBLIC_WECHAT_ENTRY_URL || '',
    sharedBotState: () => sharedBotAccounts.publicState(),
    clock,
  });

  const ingress = new SqliteIngressStore({ db, clock });
  const outbox = new SqliteReplyOutbox({ db, clock });
  const firstReply = new FirstReplyService({
    registrationService: registration,
    replyOutbox: outbox,
    encrypt: ({ scope, value }) => encryptJson({ key: payloadKey, scope, value }),
    routeBinder: ({ userId, accountId, toUserId, contextToken }) => bindReplyRoute({ routeKey, userId, botAccountId: accountId, senderId: toUserId, contextToken }),
    clock,
  });

  const tokenLedger = new GlobalDailyTokenLedger({ db, clock });
  const providerCircuit = new SqliteDeepSeekCircuitBreaker({ db, clock });
  const deepSeekRuntime = new DeepSeekV4ProRuntime({
    apiKeyProvider: async () => deepSeekApiKey,
    userIdSecret: identityKey,
    fetchImpl,
    timeoutMs: Number(env.CYBERBOSS_DEEPSEEK_TIMEOUT_MS || 300_000),
  });
  const sharedController = new SharedDeepSeekController({ seats, ledger: tokenLedger, runtime: deepSeekRuntime, circuit: providerCircuit });
  const userMessageRuntime = new UserMessageRuntime({
    sharedController,
    userRepository: users,
    replyOutbox: outbox,
    encrypt: ({ scope, value }) => encryptJson({ key: payloadKey, scope, value }),
    routeKey,
  });

  const resolveAccount = async (accountId) => {
    const account = sharedBotAccounts.getActive();
    if (!account || account.accountId !== accountId) throw Object.assign(new Error('WEIXIN_ACCOUNT_NOT_ACTIVE'), { code: 'WEIXIN_ACCOUNT_NOT_ACTIVE' });
    return account;
  };
  const dispatcher = new DurableReplyDispatcher({
    outbox,
    decrypt: ({ scope, record }) => decryptJson({ key: payloadKey, scope, record }),
    resolveAccount,
    clientFactory: (account) => new (require('../weixin/ilink-message-client').ILinkMessageClient)({ baseUrl: account.baseUrl, token: account.botToken, fetchImpl }),
  });
  const handleUserMessage = onUserMessage || ((input) => userMessageRuntime.handle(input));
  const supervisor = new WeixinAccountSupervisor({
    db, masterKey, payloadKey, ingress, firstReply, userRepository: users, onMessage: handleUserMessage, clock,
    clientFactory: (account) => new (require('../weixin/ilink-message-client').ILinkMessageClient)({ baseUrl: account.baseUrl, token: account.botToken, fetchImpl }),
  });

  const allowedHosts = String(env.CYBERBOSS_ALLOWED_HOSTS || 'cyberboss.linzezhang.com,localhost,127.0.0.1').split(',').map((value) => value.trim()).filter(Boolean);
  const accountSummary = async (userId) => ({
    channelStatus: sharedBotAccounts.publicState().status,
    ai: { provider: 'deepseek', model: 'deepseek-v4-pro', reasoningEffort: 'high', credentialMode: 'owner_shared' },
    seats: seats.snapshot(),
    usage: projectSharedDeepSeekStatus({ seats, ledger: tokenLedger, circuit: providerCircuit, now: clock() }),
  });
  const server = createPublicEntryServer({
    entryService, webSessions, ownerActivation, authorizeOwner, assetRoot, allowedHosts,
    ready: () => entryService.summary().ready,
    accountSummary,
  });
  const runtime = new MvpRuntime({ server, supervisor, replyDispatcher: dispatcher, onError: (error) => console.error(JSON.stringify({ event: 'runtime_error', code: error?.code || 'RUNTIME_ERROR' })) });

  return {
    db, users, seats, registration, webSessions, sharedBotAccounts, activationStore, ownerActivation, entryService,
    ingress, outbox, dispatcher, supervisor, tokenLedger, providerCircuit, deepSeekRuntime, sharedController,
    userMessageRuntime, server, runtime,
    close: async () => { await runtime.stop(); db.close(); },
  };
}
module.exports = { createMvpComponents, assertOwnerUserId };
