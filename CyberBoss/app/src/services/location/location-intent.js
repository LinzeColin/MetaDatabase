"use strict";

// 用大白话改自己的位置（CB9-240 / AC-015）。
//
// AC-015：「发送纠正、切换和删除语句；时区即时更新，删除后回退且派生位置不可
// 再读。」三件事：
//
//   纠正 —— 「我在东京」「不是，我在悉尼」。它猜错了，人来改。
//   切换 —— 「我到纽约了」「我回北京了」。人真的换了地方。
//   删除 —— 「别记我的位置」「忘掉我在哪」。人不想让它存这个。
//
// 这三件都必须是**确定性口令**，不能交给模型。理由和提醒那条一样：模型可能
// 调工具，也可能只是回一句「好的」然后什么都没发生——而用户以为改好了，接下
// 来所有的时间都按错的时区算，一直到他自己发现为止。
//
// 认不出来就返回 null，照旧交给模型。宁可漏判，也不能把「我在想东京的事」
// 听成一次搬家。

const { BEIJING_ZONE, isValidIanaZone } = require("../time/canonical-time");

// 城市 → IANA 时区。
//
// 中国那几个城市用 BEIJING_ZONE 常量而不是字面量：CB9-200 那条结构性守卫要求
// Asia/Shanghai 只出现在权威层里。这张表是查找表不是格式化代码，但给它开例外
// 是在给守卫开口子——用常量既不违规，也不用解释。
//
// 只收**用中文说得出口**的那些：这是个微信机器人，不是订票系统。列表短是
// 有意的——每多一个条目就多一次误判的机会，而漏掉的城市会退回到「说不出
// 时区就问一句」，代价比认错小得多。
const CITY_ZONES = Object.freeze({
  北京: BEIJING_ZONE, 上海: BEIJING_ZONE, 广州: BEIJING_ZONE,
  深圳: BEIJING_ZONE, 杭州: BEIJING_ZONE, 成都: BEIJING_ZONE,
  重庆: BEIJING_ZONE, 西安: BEIJING_ZONE, 南京: BEIJING_ZONE,
  武汉: BEIJING_ZONE, 天津: BEIJING_ZONE, 苏州: BEIJING_ZONE,
  香港: "Asia/Hong_Kong", 澳门: "Asia/Macau", 台北: "Asia/Taipei",
  东京: "Asia/Tokyo", 大阪: "Asia/Tokyo", 首尔: "Asia/Seoul",
  新加坡: "Asia/Singapore", 曼谷: "Asia/Bangkok", 吉隆坡: "Asia/Kuala_Lumpur",
  雅加达: "Asia/Jakarta", 马尼拉: "Asia/Manila", 河内: "Asia/Ho_Chi_Minh",
  迪拜: "Asia/Dubai", 孟买: "Asia/Kolkata", 新德里: "Asia/Kolkata",
  悉尼: "Australia/Sydney", 墨尔本: "Australia/Melbourne",
  布里斯班: "Australia/Brisbane", 珀斯: "Australia/Perth",
  奥克兰: "Pacific/Auckland", 惠灵顿: "Pacific/Auckland",
  伦敦: "Europe/London", 巴黎: "Europe/Paris", 柏林: "Europe/Berlin",
  阿姆斯特丹: "Europe/Amsterdam", 苏黎世: "Europe/Zurich",
  马德里: "Europe/Madrid", 罗马: "Europe/Rome", 莫斯科: "Europe/Moscow",
  纽约: "America/New_York", 华盛顿: "America/New_York",
  波士顿: "America/New_York", 多伦多: "America/Toronto",
  芝加哥: "America/Chicago", 温哥华: "America/Vancouver",
  洛杉矶: "America/Los_Angeles", 旧金山: "America/Los_Angeles",
  西雅图: "America/Los_Angeles", 圣何塞: "America/Los_Angeles",
  西雅特: "America/Los_Angeles",
});

const CITY_NAMES = Object.freeze(Object.keys(CITY_ZONES));

// 删除。放在最前面判：「别记我在哪」里也有「我在」两个字，先判纠正的话
// 会把一句删除听成「他在『哪』这个城市」。
const FORGET = /^(别记(我的)?位置|别记我在哪|忘掉我(在哪|的位置)|删掉我的位置|不要记我的位置|别存我的位置|清除我的位置)[。.!！]?$/;

// 「我现在在哪」——查询，不是修改。也要接住：不接的话模型会现编一个。
const WHERE = /^(我(现在)?在哪(儿|里)?|你(知道|觉得)我在哪(儿|里)?|我的时区是(什么|啥))[?？。.]?$/;

// 纠正/切换。两者的差别只在措辞，落库动作完全一样，所以不分开解析——
// 分开的唯一后果是多两条会互相抢的正则。
//
// 「不是」「不对」开头的是纠正；「我到了」「我回」开头的是切换。
const PLACE_PREFIX = "(?:不是[，,]?\\s*|不对[，,]?\\s*|其实\\s*)?"
  + "(?:我\\s*(?:现在|这会儿|目前)?\\s*)?"
  + "(?:在|到了?|回(?:到)?了?|来(?:到)?了?|搬到了?|飞到了?)\\s*";
const PLACE_SUFFIX = "\\s*(?:了|啦|呢)?[。.!！]?$";

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

// 城市正则**预编译一次**，不是每条消息现建 50 个。
// 每条入站消息都会走这里，现建的话是纯浪费——而且长输入上更贵。
const CITY_PATTERNS = Object.freeze(CITY_NAMES.map((city) => Object.freeze({
  city,
  timezone: CITY_ZONES[city],
  pattern: new RegExp(`^${PLACE_PREFIX}${city}${PLACE_SUFFIX}`),
})));

// 「我在悉尼」→ Australia/Sydney。
function matchPlace(text) {
  for (const entry of CITY_PATTERNS) {
    if (entry.pattern.test(text)) {
      return { city: entry.city, timezone: entry.timezone };
    }
  }
  return null;
}

// 直接说 IANA 时区名的（「我的时区是 Asia/Tokyo」）。
// 这条是给会用的人留的后门，不出现在任何提示里——新手路径不能有技术术语。
const RAW_ZONE = /^(?:我的?时区(?:是|改成|设为|设成)\s*)([A-Za-z]+\/[A-Za-z_\-+0-9]+)[。.]?$/;

function parseLocationIntent(rawText) {
  const text = normalizeText(rawText);
  // 位置这种话都很短。长句子里出现「我在东京」多半是在讲别的事
  // （「我在东京的朋友说…」），不该触发一次搬家。
  if (!text || text.length > 40) {
    return null;
  }
  if (FORGET.test(text)) {
    return Object.freeze({ kind: "forget" });
  }
  if (WHERE.test(text)) {
    return Object.freeze({ kind: "where" });
  }
  const raw = RAW_ZONE.exec(text);
  if (raw && isValidIanaZone(raw[1])) {
    return Object.freeze({ kind: "set", timezone: raw[1], city: null });
  }
  const place = matchPlace(text);
  if (place) {
    return Object.freeze({ kind: "set", timezone: place.timezone, city: place.city });
  }
  return null;
}

// 改完回的那一句。说清楚改成了什么，以及怎么撤销——「改错了怎么办」是用户
// 在这一刻唯一会想的问题。
function buildSetReply({ city, timezone }) {
  const place = city || timezone;
  return `好，记下了，你在${place}。以后跟时间有关的事我都按${place}的时间算。`
    + `（说错了直接再说一次；不想让我记就说「别记我的位置」。）`;
}

function buildForgetReply() {
  return "好，你的位置我不记了，已经删掉。时间我按北京时间算。";
}

function buildWhereReply(profile) {
  if (!profile) {
    return "我这儿没记你的位置，时间按北京时间算。想让我知道的话，直接说「我在东京」这样就行。";
  }
  const place = profile.coarse_city || profile.timezone;
  return profile.confirmed
    ? `你跟我说过你在${place}，我一直按这个算时间。`
    : `我猜你在${place}——不对的话直接告诉我你在哪儿。`;
}

module.exports = {
  CITY_ZONES,
  buildForgetReply,
  buildSetReply,
  buildWhereReply,
  parseLocationIntent,
};
