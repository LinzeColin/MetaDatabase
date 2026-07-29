"use strict";

// 「代码在不等于功能在。」这个仓第八次栽在同一件事上。
//
// 这一次：personalSiteData 写好了、注入方也传了，但 PortalHttpServer 的构造函数
// 是**按名字解构**的——它那份参数清单里没有这个名字，于是 this.personalSiteData
// 是 undefined，#handleMeData 见到 undefined 直接回 404。
//
// 单元测试当时是绿的：它们直接调 app.personalSiteData，那一层确实没问题。绿的是
// 模块的性质，不是产品的性质。上线之后 curl 一下才发现整条路是 404。
//
// 所以这一份不测任何一个处理函数**做得对不对**，只测一件事：注入进去的东西，
// 服务器到底接没接住。以后再往门户上挂新接口，这里会替我们记得这一课。

const assert = require("node:assert/strict");
const test = require("node:test");

const { PortalHttpServer } = require("../src/services/portal/portal-server");

// 每一个注入项：名字 → 一个可辨认的桩。
const INJECTED = Object.freeze([
  "adminOverview",
  "adminInvite",
  "adminOwnerClaim",
  "adminOwnerBind",
  "adminConversations",
  "adminTrace",
  "adminOps",
  "adminPersonaRead",
  "adminPersonaWrite",
  "adminInsights",
  "publicEntry",
  "publicEntryStatus",
  "adminSessionIssue",
  "adminSessionVerify",
  "adminSessionRevoke",
  "ownerActivationStart",
  "ownerActivationPoll",
  // 这两个就是这次漏掉的。
  "personalSiteLogin",
  "personalSiteData",
]);

function bootServer() {
  const options = { portal: { handle: () => ({}) } };
  for (const name of INJECTED) {
    options[name] = () => name;
  }
  return new PortalHttpServer(options);
}

test("注入进去的每一个处理函数，服务器都要真的接住", () => {
  const server = bootServer();

  const dropped = INJECTED.filter((name) => typeof server[name] !== "function");

  assert.deepEqual(
    dropped,
    [],
    "这些名字传进去了但构造函数没接——对应的路由会静默变成 404，"
    + "而单元测试照样全绿，因为它们直接调的是 app 上那一层",
  );
});

test("接住的还得是同一个，不能张冠李戴", () => {
  const server = bootServer();

  for (const name of INJECTED) {
    assert.equal(server[name](), name, `${name} 接错了对象`);
  }
});

test("没传的就是 null，不是随便造一个能跑的默认值", () => {
  // 默认值如果是个空函数，路由就会返回 200 加一堆空数据——比 404 更难查，
  // 因为页面看起来"打开了"，只是永远是空的。
  const server = new PortalHttpServer({ portal: { handle: () => ({}) } });

  assert.equal(server.personalSiteData, null);
  assert.equal(server.adminConversations, null);
});
