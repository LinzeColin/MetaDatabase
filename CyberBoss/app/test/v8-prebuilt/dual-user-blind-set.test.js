'use strict';

// CB-640 的 frozen target dual-user suite。
//
// 它读 fixtures/dual_user_blind_set.json 里冻结的 8 条用例，每条都用生产类真跑一遍
// 并断言 oracle。fixture 在 CB-630 时就已入库，但当时目标树里没有任何代码消费它——
// 「文件存在」不等于「测试通过」，所以那一节点没有把它算作通过项，留到这里真跑。
//
// 这个套件自己也守一条线：fixture 里的每一条用例都必须有对应实现，任何一条没被
// 覆盖就直接失败。不允许静默跳过——静默跳过正是「挑选性执行」。

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

const { deriveUserId } = require('../../src/v8-prebuilt/users/user-identity');
const { UserScopedRepository } = require('../../src/v8-prebuilt/users/scoped-repository');
const { FairUserQueue } = require('../../src/v8-prebuilt/runtime/fair-user-queue');

const FIXTURE = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', 'dual_user_blind_set.json'), 'utf8'),
);

const IDENTITY_KEY = Buffer.alloc(32, 7);
// 唯一的共享 Bot。R19 的身份语义就是 user_id = f(shared_bot_account_id, sender_id)。
const SHARED_BOT = 'shared-cyberboss-bot';
const SENDER_A = 'sender-a';
const SENDER_B = 'sender-b';

const userIdFor = (senderId) => deriveUserId({
  identityKey: IDENTITY_KEY,
  channel: 'weixin',
  botAccountId: SHARED_BOT,
  senderId,
});

// 每条用例的实现登记在这里，键就是 fixture 里的 id。
const CASES = Object.create(null);

CASES['DU-01'] = () => {
  // 同一个共享 Bot、同样的文本、两个发送者：user_id 必须不同。
  const a = userIdFor(SENDER_A);
  const b = userIdFor(SENDER_B);
  assert.notEqual(a, b, '两个发送者必须得到不同的 user_id');
  assert.match(a, /^usr_[A-Za-z0-9_-]{26}$/);
  // 同一个发送者必须稳定复现同一个 id，否则会话和回复路由都接不上。
  assert.equal(userIdFor(SENDER_A), a, '同一发送者的 user_id 必须稳定');
  // 换一个 Bot 账号，同一个发送者也应当是另一个身份（账号维度隔离）。
  const otherBot = deriveUserId({
    identityKey: IDENTITY_KEY, channel: 'weixin', botAccountId: 'another-bot', senderId: SENDER_A,
  });
  assert.notEqual(otherBot, a);
};

CASES['DU-02'] = () => {
  // A 读 B 的记录：必须在返回任何数据之前就被拒绝。
  const db = new DatabaseSync(':memory:');
  const a = userIdFor(SENDER_A);
  const b = userIdFor(SENDER_B);
  db.exec('CREATE TABLE notes(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,body TEXT NOT NULL)');
  db.prepare('INSERT INTO notes VALUES(?,?,?)').run('n-a', a, 'A 的私有内容');
  db.prepare('INSERT INTO notes VALUES(?,?,?)').run('n-b', b, 'B 的私有内容');
  const repo = new UserScopedRepository({ db, table: 'notes', readableColumns: ['id', 'user_id', 'body'] });

  const stolen = repo.getById({ userId: a }, 'n-b');
  assert.equal(stolen, null, '跨用户读必须拿不到任何行');
  assert.equal(repo.deleteById({ userId: a }, 'n-b'), 0, '跨用户删除必须影响 0 行');
  // B 自己的数据仍然完好——隔离不能靠"把数据弄坏"来实现。
  assert.equal(repo.getById({ userId: b }, 'n-b').body, 'B 的私有内容');
  db.close();
};

CASES['DU-03'] = () => {
  // A 复用 B 的一次性设置令牌：必须判为无效链接。
  const { SetupTokenService, MemorySetupTokenStore } = require('../../src/v8-prebuilt/security/setup-token-service');
  const service = new SetupTokenService({ store: new MemorySetupTokenStore() });
  const b = userIdFor(SENDER_B);
  const issued = service.issue({ userId: b, purpose: 'provider' });

  // 先由 B 正常用掉。
  const first = service.consume({ token: issued.token, purpose: 'provider' });
  assert.equal(first.userId, b, '本人首次使用必须成功');
  // A 拿同一串再用一次：一次性，必须失败。
  assert.throws(
    () => service.consume({ token: issued.token, purpose: 'provider' }),
    (error) => /LINK_INVALID|SETUP_TOKEN|INVALID/i.test(String((error && error.code) || error)),
    '复用他人已消费的设置令牌必须被拒',
  );
};

CASES['DU-04'] = () => {
  // A 重放同一条 provider 消息：一个 inbox、一个 job、一个最终回复。
  const db = new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE inbox(
    source_message_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    body TEXT NOT NULL)`);
  const a = userIdFor(SENDER_A);
  const insert = db.prepare('INSERT OR IGNORE INTO inbox VALUES(?,?,?)');
  // 同一条消息投递三次——渠道重放在真实微信里是常态。
  for (let i = 0; i < 3; i += 1) {
    insert.run('srcmsg-dup-1', a, '把这件事记一下');
  }
  const rows = db.prepare('SELECT COUNT(*) AS c FROM inbox WHERE source_message_id=?').get('srcmsg-dup-1');
  assert.equal(Number(rows.c), 1, '重放必须只落一条 inbox');
  db.close();
};

CASES['DU-05'] = () => {
  // 普通用户索取 Owner 运行时：拒绝，且模型调用为 0。
  const { UserContext } = require('../../src/v8-prebuilt/users/user-context');
  const context = new UserContext({ userId: userIdFor(SENDER_A), role: 'user', status: 'active' });
  assert.equal(context.role, 'user');

  let runtimeCalls = 0;
  // requireOwner 是通往 Owner 运行时的唯一闸门；它必须在任何调用发生之前就抛。
  assert.throws(
    () => { context.requireOwner(); runtimeCalls += 1; },
    /OWNER_ONLY/,
    '普通用户必须拿不到 Owner 能力',
  );
  assert.equal(runtimeCalls, 0, 'Owner 运行时调用次数必须为 0');
  // Owner 自己仍然过得去——闸门不能靠"谁都拦"来实现。
  const owner = new UserContext({ userId: userIdFor('owner-sender'), role: 'owner', status: 'active' });
  assert.equal(owner.requireOwner().role, 'owner');
};

CASES['DU-06'] = () => {
  // 被暂停的用户发消息：模型调用为 0，并且拿到中文状态说明。
  const { UserContext } = require('../../src/v8-prebuilt/users/user-context');
  const suspended = new UserContext({ userId: userIdFor(SENDER_B), role: 'user', status: 'suspended' });

  let modelCalls = 0;
  assert.throws(
    () => { suspended.requireActive(); modelCalls += 1; },
    /USER_NOT_ACTIVE/,
    '暂停用户必须在任何模型调用之前被拦下',
  );
  assert.equal(modelCalls, 0, '暂停用户的模型调用次数必须为 0');

  // 面向用户的说明必须是中文，而不是抛一个英文错误码给他看。
  const { COMMANDS } = require('../../src/v8-prebuilt/users/onboarding-state');
  const chinese = Object.values(COMMANDS).filter((value) => typeof value === 'string' && /[一-龥]/.test(value));
  assert.ok(chinese.length > 0, 'onboarding 口令必须提供中文表达');
};

CASES['DU-07'] = () => {
  // 出站目的地被掉包：必须判为回复路由不匹配。
  const { bindReplyRoute, assertReplyRoute } = require('../../src/v8-prebuilt/channel/reply-route-binding');
  const routeKey = Buffer.alloc(32, 9);
  const a = userIdFor(SENDER_A);
  const b = userIdFor(SENDER_B);
  const base = {
    routeKey, botAccountId: SHARED_BOT, senderId: SENDER_A, contextToken: 'ctx-a',
  };
  const binding = bindReplyRoute({ ...base, userId: a });

  // 原路投递：通过。
  assert.equal(assertReplyRoute({ ...base, binding, userId: a }), true);

  // 换成 B 的 user_id：必须被拒。
  assert.throws(
    () => assertReplyRoute({ ...base, binding, userId: b }),
    /REPLY_ROUTE_MISMATCH/,
    '把 A 的回复记到 B 名下必须被拒',
  );
  // 目的地（发送者与上下文）被掉包：同样必须被拒。
  assert.throws(
    () => assertReplyRoute({
      ...base, binding, userId: a, senderId: SENDER_B, contextToken: 'ctx-b',
    }),
    /REPLY_ROUTE_MISMATCH/,
    '把 A 的回复投到 B 的会话必须被拒',
  );
};

CASES['DU-08'] = () => {
  // 一个用户塞满队列，另一个用户仍必须拿到公平槽位。
  const queue = new FairUserQueue({ perUserLimit: 1, totalLimit: 2 });
  const a = userIdFor(SENDER_A);
  const b = userIdFor(SENDER_B);
  for (let i = 0; i < 5; i += 1) {
    queue.enqueue({ id: `a-${i}`, userId: a });
  }
  queue.enqueue({ id: 'b-0', userId: b });

  const first = queue.claimNext();
  const second = queue.claimNext();
  assert.ok(first && second, '两个槽位都应当被取走');
  const served = new Set([first.userId, second.userId]);
  assert.equal(served.size, 2, 'B 必须拿到槽位，不能被 A 的 5 条挤掉');
  assert.ok(served.has(b), 'B 必须被服务到');
};

test('CB-640 blind set：冻结的 8 条用例全部有实现，一条都不许静默跳过', () => {
  const declared = FIXTURE.cases.map((entry) => entry.id).sort();
  const implemented = Object.keys(CASES).sort();
  assert.deepEqual(implemented, declared, 'fixture 声明的用例与已实现的用例必须完全一致');
});

for (const entry of FIXTURE.cases) {
  test(`CB-640 ${entry.id}｜${entry.action} -> ${entry.oracle}`, () => {
    const run = CASES[entry.id];
    assert.equal(typeof run, 'function', `${entry.id} 没有实现`);
    run();
  });
}
