'use strict';
const { conservativeDeepSeekReservation } = require('./deepseek-token-reservation');

class SharedDeepSeekController {
  constructor({ seats, ledger, runtime, circuit, estimateTokens = conservativeDeepSeekReservation } = {}) {
    if (!seats || !ledger || !runtime || !circuit || typeof estimateTokens !== 'function') throw new TypeError('shared runtime dependencies are required');
    Object.assign(this, { seats, ledger, runtime, circuit, estimateTokens });
  }

  async execute({ userId, role = 'user', requestId, messages, signal }) {
    const seat = this.seats.claim({ userId, role });
    if (!seat.accepted) return Object.freeze({ ok: false, code: seat.code, providerCalls: 0 });
    let estimated;
    try { estimated = this.estimateTokens(messages); }
    catch (error) { return Object.freeze({ ok: false, code: error.code || 'INPUT_NOT_SERIALIZABLE', providerCalls: 0 }); }
    const reservation = this.ledger.reserve({ requestId, userId, estimatedTotalTokens: estimated });
    if (!reservation.accepted) return Object.freeze({ ok: false, code: reservation.code, providerCalls: 0 });
    const circuit = this.circuit.before();
    if (!circuit.allowed) {
      this.ledger.release(reservation.reservationId);
      return Object.freeze({ ok: false, code: circuit.code, providerCalls: 0 });
    }
    let dispatched = false;
    try {
      dispatched = true;
      const result = await this.runtime.send({ messages, userId, signal });
      const settlement = this.ledger.settle({ reservationId: reservation.reservationId, usage: result.usage });
      this.circuit.success();
      return Object.freeze({ ok: true, result, settlement, providerCalls: 1 });
    } catch (error) {
      this.circuit.failure({ retryable: Boolean(error.retryable), code: error.code || 'DEEPSEEK_FAILED' });
      if (!dispatched || error.preDispatch || ['OWNER_DEEPSEEK_KEY_MISSING', 'INPUT_NOT_SERIALIZABLE'].includes(error.code)) this.ledger.release(reservation.reservationId);
      else this.ledger.settle({ reservationId: reservation.reservationId, usage: null });
      return Object.freeze({ ok: false, code: error.code || 'DEEPSEEK_FAILED', providerCalls: dispatched && !error.preDispatch ? 1 : 0 });
    }
  }
}
module.exports = { SharedDeepSeekController };
