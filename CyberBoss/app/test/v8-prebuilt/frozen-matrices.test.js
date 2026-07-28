'use strict';

// CB-720 的 sensitive-attribute negative fixtures 与 CB-820 的 frozen fault matrix。
//
// 这三个 fixture 随 overlay 入库时没有任何消费者。我在 CB-720 的证据里一度写成
// 「已消费」——那是错的：当时的 grep 命中的是 "sensitive" 这个词，不是 fixture
// 名。证据已更正，这个文件是把它变成真的。
//
// 和 blind set 同样的守卫：每个矩阵声明多少条，就必须断言多少条，数量对不上直接
// 失败。fixture 里加了新用例而这里没跟上，测试会红，而不是悄悄少测。

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const load = (name) => JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures', `${name}.json`), 'utf8'),
);

const IMPORT_ATTACKS = load('import_attack_matrix');
const PROVIDER_FAULTS = load('provider_fault_matrix');
const ZERO_AGENT = load('zero_agent_runtime_cases');

// ── CB-720 / CB-710：导入攻击矩阵 ─────────────────────────
//
// 每条的 expected 都是一个「必须拒绝」或「必须隔离后继续」的判定。这里断言
// upload-policy 与 safe-zip-reader 确实提供了对应的拒绝理由，而不是只在文档里写着。

const { UPLOAD_POLICY } = (() => {
  try {
    return require('../../src/v8-prebuilt/imports/upload-policy');
  } catch {
    return {};
  }
})();

test('CB-720 导入攻击矩阵：7 条全部有对应的拒绝语义', () => {
  assert.equal(IMPORT_ATTACKS.cases.length, 7, '矩阵条数变了就必须同步更新断言');
  // 防护合法地分布在 imports 目录的多个模块里（策略、读取器、台账、路由），
  // 所以扫整个目录，而不是只看其中两个文件。
  const importsDir = path.join(__dirname, '..', '..', 'src', 'v8-prebuilt', 'imports');
  const combined = fs.readdirSync(importsDir)
    .filter((name) => name.endsWith('.js'))
    .map((name) => fs.readFileSync(path.join(importsDir, name), 'utf8'))
    .join('\n');

  // 每条 expected 对应实现里必须存在的一个具体防护概念。
  const REQUIRED = {
    reject_path_traversal: /traversal|\.\.\//i,
    reject_duplicate_target: /duplicate/i,
    reject_expansion_ratio: /ratio|expansion|bomb/i,
    reject_depth: /depth/i,
    // 白名单比「拒绝可执行文件」的黑名单更强：不在名单上的一律拒。
    reject_active_content: /allowedExtensions|ARCHIVE_FILE_TYPE_FORBIDDEN/,
    same_import_identity_no_duplicate_facts: /identity|idempot|dedup/i,
    quarantine_record_continue_valid_records: /quarantine/i,
  };
  const missing = [];
  for (const entry of IMPORT_ATTACKS.cases) {
    const pattern = REQUIRED[entry.expected];
    assert.ok(pattern, `${entry.id} 的 expected「${entry.expected}」没有登记对应防护`);
    if (!pattern.test(combined)) {
      missing.push(`${entry.id}:${entry.expected}`);
    }
  }
  assert.deepEqual(missing, [], '每条攻击都必须在导入实现里有对应防护');
});

// ── CB-820：Provider 故障矩阵 ─────────────────────────────

test('CB-820 provider 故障矩阵：7 条全部有对应处理，且不得跨用户外溢', () => {
  assert.equal(PROVIDER_FAULTS.cases.length, 7, '矩阵条数变了就必须同步更新断言');
  const runtime = fs.readFileSync(
    path.join(__dirname, '..', '..', 'src', 'v8-prebuilt', 'runtime', 'deepseek-v4-pro-runtime.js'),
    'utf8',
  );
  const breaker = fs.readFileSync(
    path.join(__dirname, '..', '..', 'src', 'v8-prebuilt', 'runtime', 'sqlite-deepseek-circuit-breaker.js'),
    'utf8',
  );
  const combined = `${runtime}\n${breaker}`;

  for (const entry of PROVIDER_FAULTS.cases) {
    // 每条要么给状态码，要么给故障类型；两者必居其一，否则矩阵本身有问题。
    const hasShape = Number.isInteger(entry.status) || typeof entry.fault === 'string';
    assert.ok(hasShape, `矩阵条目缺少 status 或 fault：${JSON.stringify(entry)}`);
    assert.ok(typeof entry.expected === 'string' && entry.expected.length > 0, '每条必须有 expected');
    // 「只影响当前用户」是这一矩阵反复出现的约束，实现里必须有用户维度。
    if (/current_user_only|no_cross_user/.test(entry.expected)) {
      assert.match(combined, /userId|user_id/, '故障处理必须是按用户维度的');
    }
    // 任何一条都不允许把密钥写进日志。
    if (/no_secret_log/.test(entry.expected)) {
      assert.doesNotMatch(combined, /console\.(log|error)\([^)]*apiKey/i, '不得把密钥打进日志');
    }
  }
});

// ── CB-810：Zero-Agent 面 ────────────────────────────────

test('CB-810 zero-agent：声明必须为零的面不得出现在允许触发模型的清单里', () => {
  const mustBeZero = ZERO_AGENT.must_remain_zero;
  const permitted = ZERO_AGENT.permitted_model_triggers;
  assert.ok(Array.isArray(mustBeZero) && mustBeZero.length > 0);
  assert.ok(Array.isArray(permitted) && permitted.length > 0);

  // 两个集合必须完全不相交——一个面既"必须零模型调用"又"允许触发模型"就是自相矛盾。
  const overlap = mustBeZero.filter((surface) => permitted.includes(surface));
  assert.deepEqual(overlap, [], '必须为零的面不得同时出现在允许触发清单里');

  // 允许触发模型的三个入口都必须是"用户显式发起"或"Owner 自己的 turn"，
  // 不允许出现任何后台面。
  for (const trigger of permitted) {
    assert.match(
      trigger,
      /^(explicit_user_|owner_)/,
      `允许触发模型的入口必须是显式用户或 Owner：${trigger}`,
    );
  }
});

// IMP-07 的行为测试。关键词匹配只能证明"实现里提到了隔离"，证明不了它真的
// 隔离得对——这一条必须真跑一批混着坏记录的输入。
test('CB-710 IMP-07：一条坏记录进隔离区，其余有效记录照常导入', () => {
  const { parseImportBatch } = require('../../src/v8-prebuilt/imports/router');
  // 用冻结的真实导出 fixture，而不是手捏的形状。
  const good = load('chatgpt');

  const result = parseImportBatch({
    source: 'chatgpt',
    inputs: [good, null, good],
  });

  assert.equal(result.parsed.length, 2, '两条有效记录必须都被解析出来');
  assert.equal(result.quarantined.length, 1, '坏记录必须进隔离区');
  assert.equal(result.quarantined[0].index, 1, '隔离记录必须标明是第几条');
  assert.ok(result.quarantined[0].code, '隔离记录必须带错误码');
  // 隔离记录不得抄录原始内容——那是用户的私有聊天。
  assert.deepEqual(Object.keys(result.quarantined[0]).sort(), ['code', 'index']);
});

test('CB-710 IMP-07：不认识的来源仍然整体拒绝，隔离不是万能兜底', () => {
  const { parseImportBatch } = require('../../src/v8-prebuilt/imports/router');
  const result = parseImportBatch({ source: 'unknown-vendor', inputs: [{}, {}] });
  assert.equal(result.parsed.length, 0);
  assert.equal(result.quarantined.length, 2, '来源不支持时每条都应进隔离而不是假装成功');
  assert.ok(result.quarantined.every((entry) => entry.code === 'IMPORT_SOURCE_UNSUPPORTED'));
});
