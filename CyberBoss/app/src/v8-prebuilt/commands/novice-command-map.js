'use strict';
const MAP=new Map([
  ['开始','onboarding.start'],['帮助','help'],['ai状态','ai.status'],['模型状态','ai.status'],['连接ai','ai.status'],
  ['导入聊天','portal.import'],['我的资料','portal.profile'],['我的记忆','portal.memory'],['最近7天','analytics.week'],
  ['设置提醒','reminder.create'],['设置','portal.home'],['退出网页','portal.revoke'],['导出我的数据','privacy.export'],
  ['删除我的数据','privacy.delete'],['停止','turn.stop'],
]);
function resolveNoviceCommand(text){return MAP.get(String(text||'').trim().toLowerCase())||null;}
module.exports={MAP,resolveNoviceCommand};
