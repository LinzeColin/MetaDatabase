'use strict';
const COMMANDS = Object.freeze({ START:'开始', CONSENT:'同意并开始', CANCEL:'退出' });
function reduceOnboarding(state, text, { inviteValidated = false } = {}) {
  const current = state || 'unseen';
  const input = String(text || '').trim();
  if (current === 'unseen' && input === COMMANDS.START) return { state:'pending_invite', action:'request_invite', modelCalls:0 };
  if (current === 'pending_invite' && inviteValidated) return { state:'pending_consent', action:'show_consent', modelCalls:0 };
  if (current === 'pending_consent' && input === COMMANDS.CONSENT) return { state:'active', action:'show_home', modelCalls:0 };
  if (['pending_invite','pending_consent'].includes(current) && input === COMMANDS.CANCEL) return { state:'unseen', action:'cancelled', modelCalls:0 };
  if (current !== 'active') return { state:current, action:'prompt_required_step', modelCalls:0 };
  return { state:'active', action:'route_active_user', modelCalls:null };
}
module.exports={COMMANDS,reduceOnboarding};
