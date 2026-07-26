const test = require("node:test");
const assert = require("node:assert/strict");

const { CyberbossApp } = require("../src/core/app");
const { TurnGateStore } = require("../src/core/turn-gate-store");

const TEST_WORKSPACE_REGISTRY = Object.freeze({
  assertAllowedRoot(root) {
    assert.equal(root, "/workspace");
    return { alias: "cyberboss", root };
  },
});

test("turn gate tracks pending scopes until the turn is released", () => {
  const gate = new TurnGateStore();
  const scopeKey = gate.begin("binding-1", "/workspace");

  assert.equal(scopeKey, "binding-1::/workspace");
  assert.equal(gate.isPending("binding-1", "/workspace"), true);

  gate.attachThread(scopeKey, "thread-1");
  gate.releaseThread("thread-1");

  assert.equal(gate.isPending("binding-1", "/workspace"), false);
});

test("handlePreparedMessage queues a normal inbound message while the scope is busy", async () => {
  const queued = [];
  let dispatched = false;
  const appLike = {
    runtimeAdapter: {
      getSessionStore() {
        return {
          buildBindingKey() {
            return "binding-1";
          },
          getThreadIdForWorkspace() {
            return "thread-1";
          },
        };
      },
    },
    threadStateStore: {
      getThreadState() {
        return { status: "running", pendingApproval: null };
      },
    },
    turnGateStore: {
      isPending() {
        return false;
      },
    },
    turnBoundaryScopeKeys: new Set(),
    streamDelivery: {
      setReplyTarget() {},
    },
    pendingInboundByScope: new Map(),
    hasPendingImageInbound() {
      return false;
    },
    resolveWorkspaceRoot() {
      return "/workspace";
    },
    async prepareIncomingMessageForRuntime(normalized) {
      return {
        ...normalized,
        text: "prepared-user-text",
      };
    },
    async dispatchPreparedTurn() {
      dispatched = true;
      return true;
    },
    bufferPendingInboundMessage({ bindingKey, workspaceRoot, prepared }) {
      queued.push({ bindingKey, workspaceRoot, ...prepared });
    },
    isTurnDispatchBlocked: CyberbossApp.prototype.isTurnDispatchBlocked,
    routePreparedInbound: CyberbossApp.prototype.routePreparedInbound,
  };

  await CyberbossApp.prototype.handlePreparedMessage.call(appLike, {
    workspaceId: "default",
    accountId: "acc-1",
    senderId: "user-1",
    contextToken: "ctx-1",
    provider: "weixin",
    text: "hello",
    receivedAt: "2026-04-13T08:00:00.000Z",
  }, { allowCommands: true });

  assert.equal(dispatched, false);
  assert.equal(queued.length, 1);
  assert.equal(queued[0].bindingKey, "binding-1");
  assert.equal(queued[0].workspaceRoot, "/workspace");
  assert.equal(queued[0].text, "prepared-user-text");
});

test("dispatchSystemMessage yields when a local pending turn already owns the workspace thread", async () => {
  let handled = false;
  const appLike = {
    workspaceRegistry: TEST_WORKSPACE_REGISTRY,
    systemMessageDispatcher: {
      buildPreparedMessage() {
        return {
          workspaceId: "default",
          accountId: "acc-1",
          senderId: "user-1",
          workspaceRoot: "/workspace",
        };
      },
    },
    channelAdapter: {
      getKnownContextTokens() {
        return { "user-1": "ctx-1" };
      },
    },
    runtimeAdapter: {
      getSessionStore() {
        return {
          buildBindingKey() {
            return "binding-1";
          },
          getThreadIdForWorkspace() {
            return "thread-1";
          },
        };
      },
    },
    threadStateStore: {
      getThreadState() {
        return null;
      },
    },
    turnGateStore: {
      isPending() {
        return true;
      },
    },
    turnBoundaryScopeKeys: new Set(),
    resolveWorkspaceRoot() {
      return "/workspace";
    },
    async handlePreparedMessage() {
      handled = true;
    },
    isTurnDispatchBlocked: CyberbossApp.prototype.isTurnDispatchBlocked,
  };

  const dispatched = await CyberbossApp.prototype.dispatchSystemMessage.call(appLike, {
    senderId: "user-1",
    id: "system-1",
    text: "ping",
  });

  assert.equal(dispatched, false);
  assert.equal(handled, false);
});

test("handlePreparedMessage queues while the scope is in a turn-boundary handoff", async () => {
  const queued = [];
  let dispatched = false;
  const appLike = {
    runtimeAdapter: {
      getSessionStore() {
        return {
          buildBindingKey() {
            return "binding-1";
          },
          getThreadIdForWorkspace() {
            return "thread-1";
          },
        };
      },
    },
    threadStateStore: {
      getThreadState() {
        return { status: "completed", pendingApproval: null };
      },
    },
    turnGateStore: {
      isPending() {
        return false;
      },
    },
    turnBoundaryScopeKeys: new Set(["binding-1::/workspace"]),
    streamDelivery: {
      setReplyTarget() {},
    },
    pendingInboundByScope: new Map(),
    hasPendingImageInbound() {
      return false;
    },
    resolveWorkspaceRoot() {
      return "/workspace";
    },
    async prepareIncomingMessageForRuntime(normalized) {
      return {
        ...normalized,
        text: "prepared-user-text",
      };
    },
    async dispatchPreparedTurn() {
      dispatched = true;
      return true;
    },
    bufferPendingInboundMessage({ bindingKey, workspaceRoot, prepared }) {
      queued.push({ bindingKey, workspaceRoot, ...prepared });
    },
    isTurnDispatchBlocked: CyberbossApp.prototype.isTurnDispatchBlocked,
    routePreparedInbound: CyberbossApp.prototype.routePreparedInbound,
  };

  await CyberbossApp.prototype.handlePreparedMessage.call(appLike, {
    workspaceId: "default",
    accountId: "acc-1",
    senderId: "user-1",
    contextToken: "ctx-1",
    provider: "weixin",
    text: "hello",
    receivedAt: "2026-04-13T08:00:00.000Z",
  }, { allowCommands: true });

  assert.equal(dispatched, false);
  assert.equal(queued.length, 1);
});

test("dispatchPreparedTurn binds reply target to the explicit turn id when runtime returns one", async () => {
  const turnBindings = [];
  const queuedBindings = [];
  const order = [];
  const appLike = {
    workspaceRegistry: TEST_WORKSPACE_REGISTRY,
    channelAdapter: {
      async sendTyping() {
        order.push("typing");
      },
      async sendText() {},
    },
    turnGateStore: {
      begin() {
        order.push("begin");
        return "binding-1::/workspace";
      },
      attachThread() {},
      releaseScope() {},
    },
    runtimeAdapter: {
      async sendTextTurn() {
        return { threadId: "thread-1", turnId: "turn-1" };
      },
      getSessionStore() {
        return {
          getRuntimeParamsForWorkspace() {
            return { model: "gpt-5.4" };
          },
        };
      },
    },
    async buildRuntimeTurn({ prepared }) {
      return {
        text: prepared.text,
        attachments: [],
      };
    },
    streamDelivery: {
      bindReplyTargetForTurn(payload) {
        turnBindings.push(payload);
      },
      queueReplyTargetForThread(threadId, target) {
        queuedBindings.push({ threadId, target });
      },
    },
  };

  const dispatched = await CyberbossApp.prototype.dispatchPreparedTurn.call(appLike, {
    bindingKey: "binding-1",
    workspaceRoot: "/workspace",
    prepared: {
      workspaceId: "default",
      accountId: "acc-1",
      senderId: "user-1",
      contextToken: "ctx-1",
      provider: "system",
      text: "ping",
    },
  });

  assert.equal(dispatched, true);
  assert.deepEqual(turnBindings, [{
    threadId: "thread-1",
    turnId: "turn-1",
    target: {
      userId: "user-1",
      contextToken: "ctx-1",
      provider: "system",
    },
  }]);
  assert.deepEqual(queuedBindings, []);
  assert.deepEqual(order, ["begin", "typing"]);
});

test("completed turns flush queued inbound work before system messages", async () => {
  const calls = [];
  const appLike = {
    streamDelivery: {
      async handleRuntimeEvent() {},
    },
    runtimeAdapter: {
      getSessionStore() {
        return {
          clearApprovalPrompt() {},
          findBindingForThreadId() {
            return {
              bindingKey: "binding-1",
              workspaceRoot: "/workspace",
            };
          },
        };
      },
    },
    turnGateStore: {
      releaseThread() {
        calls.push("releaseThread");
      },
      isPending() {
        return false;
      },
    },
    turnBoundaryScopeKeys: new Set(),
    hasPendingInboundMessage() {
      return false;
    },
    async stopTypingForThread() {
      calls.push("stopTyping");
    },
    async sendFailureToThread() {
      calls.push("sendFailure");
    },
    async flushPendingInboundMessages({ ignoreBoundary } = {}) {
      calls.push(`flushInbound:${ignoreBoundary ? "ignoreBoundary" : "default"}`);
    },
    async flushPendingSystemMessages() {
      calls.push("flushSystem");
    },
  };

  await CyberbossApp.prototype.handleRuntimeEvent.call(appLike, {
    type: "runtime.turn.completed",
    payload: { threadId: "thread-1", turnId: "turn-1" },
  });

  assert.deepEqual(calls, ["releaseThread", "flushInbound:ignoreBoundary", "flushSystem", "stopTyping"]);
});

test("completed turns keep the boundary closed until queued inbound work has been flushed", async () => {
  const calls = [];
  const appLike = {
    streamDelivery: {
      async handleRuntimeEvent() {},
    },
    runtimeAdapter: {
      getSessionStore() {
        return {
          clearApprovalPrompt() {},
          findBindingForThreadId() {
            return {
              bindingKey: "binding-1",
              workspaceRoot: "/workspace",
            };
          },
        };
      },
    },
    turnGateStore: {
      releaseThread() {
        calls.push("releaseThread");
      },
      isPending() {
        return false;
      },
    },
    turnBoundaryScopeKeys: new Set(),
    hasPendingInboundMessage() {
      return true;
    },
    async stopTypingForThread() {
      calls.push("stopTyping");
    },
    async sendFailureToThread() {},
    async flushPendingInboundMessages({ ignoreBoundary } = {}) {
      calls.push(`flushInbound:${ignoreBoundary ? "ignoreBoundary" : "default"}`);
      assert.equal(this.turnBoundaryScopeKeys.has("binding-1::/workspace"), true);
    },
    async flushPendingSystemMessages() {
      calls.push("flushSystem");
    },
  };

  await CyberbossApp.prototype.handleRuntimeEvent.call(appLike, {
    type: "runtime.turn.completed",
    payload: { threadId: "thread-1", turnId: "turn-1" },
  });

  assert.deepEqual(calls, ["releaseThread", "flushInbound:ignoreBoundary", "flushSystem"]);
  assert.equal(appLike.turnBoundaryScopeKeys.has("binding-1::/workspace"), false);
});

test("completed turns flush queued inbound work before system messages", async () => {
  const calls = [];
  const appLike = {
    streamDelivery: {
      async handleRuntimeEvent() {},
    },
    runtimeAdapter: {
      getSessionStore() {
        return {
          clearApprovalPrompt() {},
          findBindingForThreadId() {
            return null;
          },
        };
      },
    },
    turnGateStore: {
      releaseThread() {
        calls.push("releaseThread");
      },
      isPending() {
        return false;
      },
    },
    turnBoundaryScopeKeys: new Set(),
    hasPendingInboundMessage() {
      return false;
    },
    async stopTypingForThread() {
      calls.push("stopTyping");
    },
    async sendFailureToThread() {
      calls.push("sendFailure");
    },
    async flushPendingInboundMessages() {
      calls.push("flushInbound");
    },
    async flushPendingSystemMessages() {
      calls.push("flushSystem");
    },
  };

  await CyberbossApp.prototype.handleRuntimeEvent.call(appLike, {
    type: "runtime.turn.completed",
    payload: { threadId: "thread-1", turnId: "turn-1" },
  });

  assert.deepEqual(calls, ["releaseThread", "flushInbound", "flushSystem", "stopTyping"]);
});

test("failed turns still send error back when thread binding lookup is missing", async () => {
  const sent = [];
  const appLike = {
    streamDelivery: {
      resolveReplyTargetForRun() {
        return {
          userId: "user-1",
          contextToken: "ctx-1",
          provider: "weixin",
        };
      },
      async handleRuntimeEvent() {},
    },
    runtimeAdapter: {
      getSessionStore() {
        return {
          clearApprovalPrompt() {},
          findBindingForThreadId() {
            return null;
          },
          getBinding() {
            return null;
          },
        };
      },
    },
    turnGateStore: {
      releaseThread() {},
      isPending() {
        return false;
      },
    },
    turnBoundaryScopeKeys: new Set(),
    hasPendingInboundMessage() {
      return false;
    },
    channelAdapter: {
      async sendText(payload) {
        sent.push(payload);
      },
    },
    async sendFailureToThread(threadId, text, fallbackTarget) {
      return CyberbossApp.prototype.sendFailureToThread.call(this, threadId, text, fallbackTarget);
    },
    async stopTypingForThread() {},
    async flushPendingInboundMessages() {},
    async flushPendingSystemMessages() {},
    resolveReplyTargetForBinding() {
      return null;
    },
  };

  await CyberbossApp.prototype.handleRuntimeEvent.call(appLike, {
    type: "runtime.turn.failed",
    payload: {
      threadId: "thread-1",
      turnId: "turn-1",
      text: "❌ Execution failed\ncontext window exceeded",
    },
  });

  assert.deepEqual(sent, [{
    userId: "user-1",
    text: "❌ Execution failed\ncontext window exceeded",
    contextToken: "ctx-1",
  }]);
});

test("flushPendingInboundMessages batches queued messages from the same scope into one turn", async () => {
  const dispatched = [];
  const scopeKey = "binding-1::/workspace";
  const appLike = {
    pendingInboundByScope: new Map([[
      scopeKey,
      {
        bindingKey: "binding-1",
        workspaceRoot: "/workspace",
        messages: [
          {
            workspaceId: "default",
            accountId: "acc-1",
            senderId: "user-1",
            messageId: "102",
            contextToken: "ctx-1",
            provider: "weixin",
            text: "[2026-04-13 16:01]\n第二条",
            receivedAt: "2026-04-13T08:00:02.000Z",
          },
          {
            workspaceId: "default",
            accountId: "acc-1",
            senderId: "user-1",
            messageId: "101",
            contextToken: "ctx-2",
            provider: "weixin",
            text: "[2026-04-13 16:00]\n第一条",
            receivedAt: "2026-04-13T08:00:01.000Z",
          },
        ],
      },
    ]]),
    isTurnDispatchBlocked() {
      return false;
    },
    async dispatchPreparedTurn(payload) {
      dispatched.push(payload);
      return true;
    },
    mergePendingInboundDraft: CyberbossApp.prototype.mergePendingInboundDraft,
  };

  await CyberbossApp.prototype.flushPendingInboundMessages.call(appLike);

  assert.equal(dispatched.length, 1);
  assert.equal(dispatched[0].prepared.contextToken, "ctx-1");
  assert.match(dispatched[0].prepared.text, /Multiple newer WeChat messages arrived/);
  assert.match(dispatched[0].prepared.text, /第一条[\s\S]*第二条/);
});

test("flushPendingInboundMessages falls back to messageId ordering when receivedAt ties", async () => {
  const dispatched = [];
  const appLike = {
    pendingInboundByScope: new Map([[
      "binding-1::/workspace",
      {
        bindingKey: "binding-1",
        workspaceRoot: "/workspace",
        messages: [
          {
            workspaceId: "default",
            accountId: "acc-1",
            senderId: "user-1",
            messageId: "200",
            contextToken: "ctx-200",
            provider: "weixin",
            text: "第三条",
            receivedAt: "2026-04-13T08:00:01.000Z",
          },
          {
            workspaceId: "default",
            accountId: "acc-1",
            senderId: "user-1",
            messageId: "198",
            contextToken: "ctx-198",
            provider: "weixin",
            text: "第一条",
            receivedAt: "2026-04-13T08:00:01.000Z",
          },
          {
            workspaceId: "default",
            accountId: "acc-1",
            senderId: "user-1",
            messageId: "199",
            contextToken: "ctx-199",
            provider: "weixin",
            text: "第二条",
            receivedAt: "2026-04-13T08:00:01.000Z",
          },
        ],
      },
    ]]),
    isTurnDispatchBlocked() {
      return false;
    },
    async dispatchPreparedTurn(payload) {
      dispatched.push(payload);
      return true;
    },
    mergePendingInboundDraft: CyberbossApp.prototype.mergePendingInboundDraft,
  };

  await CyberbossApp.prototype.flushPendingInboundMessages.call(appLike);

  assert.equal(dispatched.length, 1);
  assert.equal(dispatched[0].prepared.contextToken, "ctx-200");
  assert.match(dispatched[0].prepared.text, /第一条[\s\S]*第二条[\s\S]*第三条/);
});

test("durable stop acknowledges only the Runtime request and keeps terminal truth pending", async () => {
  const cancellations = [];
  const sent = [];
  const appLike = {
    workspaceRegistry: {
      resolve(alias) {
        assert.equal(alias, "cyberboss");
        return { alias, root: "/workspace" };
      },
    },
    runtimeAdapter: {
      getSessionStore() {
        return {
          buildBindingKey() {
            return "binding-1";
          },
        };
      },
      async cancelTurn(payload) {
        cancellations.push(payload);
      },
    },
    streamDelivery: {
      setReplyTarget() {},
    },
    channelAdapter: {
      async sendText(payload) {
        sent.push(payload.text);
      },
    },
  };

  const result = await CyberbossApp.prototype.dispatchDurableControlJob.call(
    appLike,
    {
      normalized: {
        provider: "weixin",
        workspaceId: "default",
        accountId: "account-1",
        senderId: "user-1",
        contextToken: "ctx-1",
      },
      command: { name: "stop", args: "" },
      workspace: { alias: "cyberboss", root: "/workspace" },
      activeRun: {
        job: { workspace_alias: "cyberboss" },
        threadId: "thread-1",
        turnId: "turn-1",
        runBound: true,
      },
    },
  );

  assert.deepEqual(cancellations, [{
    threadId: "thread-1",
    turnId: "turn-1",
    workspaceRoot: "/workspace",
  }]);
  assert.equal(result.resultCode, "cancel_acknowledged");
  assert.match(sent[0], /final job state is pending/);
  assert.doesNotMatch(sent[0], /job (?:cancelled|succeeded)/i);
});

test("durable bind and new commands cannot change scope during an active Runtime job", async () => {
  const sent = [];
  let commandDispatches = 0;
  const appLike = {
    runtimeAdapter: {
      getSessionStore() {
        return {
          buildBindingKey() {
            return "binding-1";
          },
        };
      },
    },
    streamDelivery: {
      setReplyTarget() {},
    },
    channelAdapter: {
      async sendText(payload) {
        sent.push(payload.text);
      },
    },
    async dispatchChannelCommand() {
      commandDispatches += 1;
    },
  };
  const normalized = {
    provider: "weixin",
    workspaceId: "default",
    accountId: "account-1",
    senderId: "user-1",
    contextToken: "ctx-1",
  };
  for (const name of ["bind", "new"]) {
    const result = await CyberbossApp.prototype.dispatchDurableControlJob.call(
      appLike,
      {
        normalized,
        command: { name, args: name === "bind" ? "cyberboss" : "" },
        activeRun: {
          job: { workspace_alias: "cyberboss" },
          runBound: true,
        },
        workspace: { alias: "cyberboss", root: "/workspace" },
      },
    );
    assert.equal(result.resultCode, "active_runtime_guard");
  }
  assert.equal(commandDispatches, 0);
  assert.equal(sent.length, 2);
});

test("durable Runtime dispatch revalidates alias and returns the exact run binding", async () => {
  const activeRoots = [];
  const appLike = {
    workspaceRegistry: {
      resolve(alias) {
        assert.equal(alias, "cyberboss");
        return { alias, root: "/workspace" };
      },
    },
    runtimeAdapter: {
      describe() {
        return { id: "codex" };
      },
      getSessionStore() {
        return {
          buildBindingKey() {
            return "binding-1";
          },
          setActiveWorkspaceRoot(bindingKey, workspaceRoot) {
            activeRoots.push([bindingKey, workspaceRoot]);
          },
        };
      },
    },
    streamDelivery: {
      setReplyTarget() {},
    },
    async prepareIncomingMessageForRuntime(normalized, workspaceRoot) {
      assert.equal(workspaceRoot, "/workspace");
      return { ...normalized };
    },
    async dispatchPreparedTurn(payload) {
      assert.equal(payload.workspaceRoot, "/workspace");
      assert.equal(payload.returnRun, true);
      return { threadId: "thread-1", turnId: "turn-1" };
    },
  };
  const run = await CyberbossApp.prototype.dispatchDurableRuntimeJob.call(
    appLike,
    {
      job: {
        runtime: "codex",
        workspace_alias: "cyberboss",
      },
      normalized: {
        provider: "weixin",
        workspaceId: "default",
        accountId: "account-1",
        senderId: "user-1",
        contextToken: "ctx-1",
      },
      workspace: { alias: "cyberboss", root: "/workspace" },
    },
  );
  assert.deepEqual(run, { threadId: "thread-1", turnId: "turn-1" });
  assert.deepEqual(activeRoots, [["binding-1", "/workspace"]]);
});
