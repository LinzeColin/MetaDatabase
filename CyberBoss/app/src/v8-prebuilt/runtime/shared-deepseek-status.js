'use strict';
function projectSharedDeepSeekStatus({ seats, ledger, circuit, counters = {}, now = Date.now() }) {
  const seat = seats.snapshot(); const usage = ledger.status(now); const providerCircuit = circuit.snapshot();
  return Object.freeze({
    schemaVersion: 'cyberboss.deepseek_shared_runtime_status.v1',
    generatedAt: new Date(now).toISOString(),
    provider: 'deepseek',
    model: 'deepseek-v4-pro',
    thinking: 'enabled',
    reasoningEffort: 'high',
    credentialMode: 'owner_deepseek_api_key',
    activeOrdinarySeats: seat.activeOrdinarySeats,
    seatLimit: seat.seatLimit,
    remainingSeats: seat.remainingSeats,
    utcDay: usage.day,
    capTokens: usage.capTokens,
    usedTokens: usage.usedTokens,
    reservedTokens: usage.reservedTokens,
    remainingTokens: usage.remainingTokens,
    promptTokens: usage.promptTokens,
    cacheHitTokens: usage.cacheHitTokens,
    cacheMissTokens: usage.cacheMissTokens,
    completionTokens: usage.completionTokens,
    reasoningTokens: usage.reasoningTokens,
    calls: usage.calls,
    fallbackCharges: usage.fallbackCharges,
    estimatedCostCny: Number(usage.estimatedCostCny.toFixed(6)),
    reservationOverrunTokens: usage.reservationOverrunTokens,
    accountingIntegrityViolations: usage.accountingIntegrityViolations,
    rejectionsGlobalCap: Number(counters.rejectionsGlobalCap || 0),
    rejectionsSeatFull: Number(counters.rejectionsSeatFull || 0),
    providerCircuit,
  });
}
module.exports = { projectSharedDeepSeekStatus };
