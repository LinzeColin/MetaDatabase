"use strict";

// 「有人反应说是 deepseek，这是不允许的，前面 5 个人都需要是 gpt 模型。」
//
// 投诉是准确的：ownerProviderCredential 里 providerId、model、密钥名三样全写死
// 成了 deepseek。换模型必须改代码重新部署——一个要卖出去的产品不该这样。

const assert = require("node:assert/strict");
const test = require("node:test");

const { ProviderRouter } = require("../src/services/providers/router");
const { DEFAULT_PROVIDER_POLICIES } = require("../src/core/user-turn-runtime");

test("推理档位真的到得了适配器——路由是按名字解构的", async () => {
  let sent = null;
  const router = new ProviderRouter({
    policies: DEFAULT_PROVIDER_POLICIES,
    fetchImpl: async (_url, init) => {
      sent = JSON.parse(init.body);
      // 适配器读的是 response.text()，不是 .json()。照着它真的调什么来造。
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({
          output: [{ content: [{ type: "output_text", text: "好" }] }],
        }),
      };
    },
  });

  await router.sendText({
    providerId: "openai",
    apiKey: "sk-test",
    model: "gpt-5",
    messages: [{ role: "user", content: "在吗" }],
    maxOutputTokens: 100,
    reasoningEffort: "high",
  });

  assert.deepEqual(
    sent.reasoning,
    { effort: "high" },
    "路由那一层漏了这个名字的话，配的档位到不了 OpenAI，而且一声不响",
  );
});

test("没给档位就不带这个字段——不认它的模型收到会直接报错", async () => {
  let sent = null;
  const router = new ProviderRouter({
    policies: DEFAULT_PROVIDER_POLICIES,
    fetchImpl: async (_url, init) => {
      sent = JSON.parse(init.body);
      // 适配器读的是 response.text()，不是 .json()。照着它真的调什么来造。
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({
          output: [{ content: [{ type: "output_text", text: "好" }] }],
        }),
      };
    },
  });

  await router.sendText({
    providerId: "openai",
    apiKey: "sk-test",
    model: "gpt-5",
    messages: [{ role: "user", content: "在吗" }],
    maxOutputTokens: 100,
  });

  assert.ok(!("reasoning" in sent), "带了空的 reasoning，等于让所有人都收不到回复");
});

test("配置里的模型没进白名单的话，每一轮都会被 MODEL_NOT_ALLOWED 挡掉", () => {
  // 这是"配了新模型结果全员静默"的确切机制：白名单是服务端拥有的，
  // assertModel 不认的 model 一律拒。所以运营者配的那一个必须并进去。
  const source = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../src/core/app.js"), "utf8",
  );
  assert.match(source, /function buildProviderPolicies\(config\)/);
  assert.match(source, /providerPolicies: buildProviderPolicies\(this\.config\)/);
});

test("找钥匙按优先级：配了 OpenAI 就不再用 DeepSeek", () => {
  const source = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../src/core/app.js"), "utf8",
  );
  const body = source.slice(source.indexOf("ownerProviderCredential()"));
  assert.ok(
    body.indexOf("OPENAI_API_KEY") < body.indexOf("DEEPSEEK_API_KEY"),
    "DeepSeek 排在 OpenAI 前面的话，配了 OpenAI 也换不过去",
  );
});
