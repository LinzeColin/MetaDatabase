#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const fixturePath = path.join(__dirname, '..', 'config', 'cloudflare-access-policy.fixture.json');
const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));

function validatePolicy(value) {
  assert.equal(value.application.type, 'self_hosted');
  assert.equal(value.application.domain, 'cyberboss.linzezhang.com');
  assert.equal(value.fixture_only, true);
  assert.equal(value.contains_real_identity, false);
  assert.equal(value.contains_real_token, false);
  assert.ok(value.policies.length >= 2);
  for (const policy of value.policies) {
    assert.ok(['allow', 'non_identity'].includes(policy.decision));
    assert.notEqual(policy.decision, 'bypass');
    for (const rule of policy.include || []) {
      assert.equal(Object.hasOwn(rule, 'everyone'), false);
      assert.equal(Object.hasOwn(rule, 'any_valid_service_token'), false);
      if (policy.decision === 'non_identity') {
        assert.equal(typeof rule.service_token?.token_id, 'string');
        assert.notEqual(rule.service_token.token_id.length, 0);
      }
    }
  }
}

function evaluate(value, request) {
  if (!request.authenticated) return 'deny';
  for (const policy of value.policies) {
    for (const rule of policy.include || []) {
      if (rule.email?.email && request.email === rule.email.email) return 'allow';
      if (
        rule.service_token?.token_id &&
        request.service_token_id === rule.service_token.token_id
      ) return 'allow';
    }
  }
  return 'deny';
}

test('fixture is fail closed and contains no real identity or token', () => {
  validatePolicy(fixture);
});

for (const item of fixture.expected_cases) {
  test(`${item.case} => ${item.expected}`, () => {
    assert.equal(evaluate(fixture, item), item.expected);
  });
}

test('bypass decision is rejected', () => {
  const hostile = structuredClone(fixture);
  hostile.policies[0].decision = 'bypass';
  assert.throws(() => validatePolicy(hostile));
});

test('Everyone include is rejected', () => {
  const hostile = structuredClone(fixture);
  hostile.policies[0].include = [{ everyone: {} }];
  assert.throws(() => validatePolicy(hostile));
});

test('any valid service token include is rejected', () => {
  const hostile = structuredClone(fixture);
  hostile.policies[1].include = [{ any_valid_service_token: {} }];
  assert.throws(() => validatePolicy(hostile));
});
