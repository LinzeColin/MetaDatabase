'use strict';
class UserContext {
  constructor({ userId, role = 'user', status = 'active', channel = 'weixin', principalHash }) {
    if (!/^usr_[A-Za-z0-9_-]{20,}$/.test(userId || '')) throw new TypeError('invalid userId');
    if (!['owner','user'].includes(role)) throw new TypeError('invalid role');
    if (!['pending_consent','active','suspended','deleting','deleted'].includes(status)) throw new TypeError('invalid status');
    this.userId=userId; this.role=role; this.status=status; this.channel=channel; this.principalHash=principalHash;
    Object.freeze(this);
  }
  requireActive(){ if(this.status!=='active') throw Object.assign(new Error('USER_NOT_ACTIVE'),{code:'USER_NOT_ACTIVE'}); return this; }
  requireOwner(){ this.requireActive(); if(this.role!=='owner') throw Object.assign(new Error('OWNER_ONLY'),{code:'OWNER_ONLY'}); return this; }
}
module.exports={UserContext};
