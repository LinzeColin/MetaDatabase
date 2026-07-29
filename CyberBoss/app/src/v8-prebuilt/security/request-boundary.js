'use strict';

function resolveServerOwnedUser({ principal, userRepository }) {
  if (!principal || !principal.botAccountId || !principal.senderId) {
    throw Object.assign(new Error('PRINCIPAL_REQUIRED'), { code: 'PRINCIPAL_REQUIRED' });
  }
  const user = userRepository.resolveByPrincipal(principal);
  if (!user) throw Object.assign(new Error('USER_NOT_FOUND'), { code: 'USER_NOT_FOUND' });
  if (user.status !== 'active') {
    throw Object.assign(new Error('USER_NOT_ACTIVE'), { code: 'USER_NOT_ACTIVE' });
  }
  return Object.freeze({ userId: user.userId, role: user.role, status: user.status });
}

function assertOwnerCapability(userContext, capability) {
  const ownerOnly = new Set(['codex.turn', 'workspace.read', 'workspace.write', 'shell.execute', 'ops.manage']);
  if (ownerOnly.has(capability) && userContext.role !== 'owner') {
    throw Object.assign(new Error('OWNER_ONLY_CAPABILITY'), { code: 'OWNER_ONLY_CAPABILITY' });
  }
  return true;
}

function requireSameUser(userContext, record) {
  if (!record || record.userId !== userContext.userId) {
    throw Object.assign(new Error('USER_SCOPE_VIOLATION'), { code: 'USER_SCOPE_VIOLATION' });
  }
  return record;
}

module.exports = { resolveServerOwnedUser, assertOwnerCapability, requireSameUser };
