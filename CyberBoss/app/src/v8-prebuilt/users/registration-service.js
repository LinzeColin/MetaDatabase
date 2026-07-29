'use strict';

class RegistrationService {
  constructor({ userRepository, inviteStore = null, seatRegistry = null, registrationMode = 'open', policyVersion = 'privacy-v1' }) {
    if (!['invite','open'].includes(registrationMode)) throw new TypeError('invalid registration mode');
    this.users = userRepository; this.invites = inviteStore; this.seats = seatRegistry; this.mode = registrationMode; this.policyVersion = policyVersion;
  }

  start({ principal, inviteCode = null }) {
    const existing = this.users.resolveByPrincipal(principal);
    if (existing) return { user: existing, action: existing.status === 'active' ? 'show_home' : 'show_consent' };
    if (this.mode === 'invite') {
      if (!this.invites || !inviteCode) return { user: null, action: 'request_invite_code' };
      this.invites.consume(inviteCode);
    }
    // Pending identities never consume a scarce ordinary-user seat.
    const user = this.users.ensurePending({ principal });
    return { user, action: 'show_consent' };
  }

  consent({ principal, accepted }) {
    const user = this.users.resolveByPrincipal(principal);
    if (!user) throw Object.assign(new Error('START_REQUIRED'), { code: 'START_REQUIRED' });
    if (!accepted) return { user, action: 'consent_declined' };
    if (user.role !== 'owner' && this.seats) {
      const seat = this.seats.claim({ userId: user.userId, role: user.role });
      if (!seat.accepted) return { user, action: 'capacity_full', code: seat.code };
      try {
        const active = user.status === 'active' ? user : this.users.activateConsent({ userId: user.userId, policyVersion: this.policyVersion });
        return { user: active, action: 'show_home', seat };
      } catch (error) {
        if (!seat.existing) this.seats.revoke(user.userId);
        throw error;
      }
    }
    const active = user.status === 'active' ? user : this.users.activateConsent({ userId: user.userId, policyVersion: this.policyVersion });
    return { user: active, action: 'show_home', seat: null };
  }

  activateFromStart({ principal, inviteCode = null }) {
    const started = this.start({ principal, inviteCode });
    if (started.action === 'request_invite_code') return started;
    if (started.user?.status === 'active') {
      const ensured = this.seats && started.user.role !== 'owner'
        ? this.seats.claim({ userId: started.user.userId, role: started.user.role })
        : { accepted: true, existing: true };
      if (!ensured.accepted) return { user: started.user, action: 'capacity_full', code: ensured.code };
      return { user: started.user, action: 'show_home', seat: ensured };
    }
    return this.consent({ principal, accepted: true });
  }
}
module.exports = { RegistrationService };
