// weread-port 的生产环境变量活在版本控制之外：wrangler.jsonc 里一个都没有，
// 而 `wrangler deploy` 会用配置文件的内容替换掉线上 vars。2026-08-12 裸跑一次
// 就把 8 个变量全清了，站点当场「账户服务尚未完成安全连接」，靠 rollback 恢复。
//
// 这个文件只放判断，不做 IO —— 判断能被反例打红，才算有闸门。

/** 线上必须存在、且部署时必须原样带回去的 plain_text 变量。少一个就不许部署。 */
export const REQUIRED_VARS = Object.freeze([
  "DEPLOYMENT_ENV",
  "WEREAD_ACCOUNT_SERVICE_URL",
  "WRP_ACCOUNT_PROXY_TIMEOUT_MS",
  "WRP_EDGE_DEPLOYMENT_ID",
  "WRP_OVH_RELEASE_ID",
  "WRP_PUBLIC_HOST",
  "WRP_RELEASE_COMMIT",
  "WRP_TASKPACK_VERSION",
]);

/** secret 由 Cloudflare 自己保留，不许也不必重新传；出现在这里就是配错了。 */
export const PRESERVED_SECRETS = Object.freeze(["WRP_INTERNAL_PROXY_SECRET"]);

/**
 * 从 /deployments 里挑出**当前正在跑的那一版**。
 * 别用 [0] 也别用 .at(-1)：`wrangler deployments list` 打印出来是升序（最老在前），
 * 而 REST API 返回的是降序（最新在前）—— 我第一版按 wrangler 的顺序写成 .at(-1)，
 * 读到的是 2026-08-02 最早那一版，于是报「线上缺 8 个变量」拒绝部署。
 * 按 created_on 排，不依赖任何一端的顺序约定。
 */
export function pickCurrentDeployment(deployments) {
  const rows = (Array.isArray(deployments) ? deployments : [])
    .filter(d => d?.versions?.[0]?.version_id)
    .map(d => ({ versionId: d.versions[0].version_id, createdOn: Date.parse(d.created_on ?? "") || 0 }))
    .sort((a, b) => b.createdOn - a.createdOn);
  if (!rows.length) throw new Error("取不到当前线上版本 id。");
  return rows[0].versionId;
}

/** 从某个 worker 版本的 bindings 里取出 plain_text 变量（name -> value）。 */
export function collectPlainTextVars(bindings) {
  const vars = new Map();
  for (const binding of Array.isArray(bindings) ? bindings : []) {
    if (binding?.type !== "plain_text") continue;
    if (typeof binding.name !== "string" || !binding.name) continue;
    vars.set(binding.name, typeof binding.text === "string" ? binding.text : "");
  }
  return vars;
}

/**
 * 部署前：线上这一版必须齐全，否则不许部署。
 * 失败方向是「不部署」，不是「先发了再说」—— 缺变量的部署会当场打断站点。
 */
export function assertCarryableVars(vars) {
  const missing = REQUIRED_VARS.filter(name => !vars.has(name));
  const empty = REQUIRED_VARS.filter(name => vars.has(name) && String(vars.get(name)).trim() === "");
  if (missing.length || empty.length) {
    const parts = [];
    if (missing.length) parts.push(`线上缺少变量：${missing.join("、")}`);
    if (empty.length) parts.push(`线上变量为空：${empty.join("、")}`);
    throw new Error(`${parts.join("；")}。不部署 —— 带不全变量的部署会打断站点。`);
  }
  const secretsAsPlainText = PRESERVED_SECRETS.filter(name => vars.has(name));
  if (secretsAsPlainText.length) {
    throw new Error(`${secretsAsPlainText.join("、")} 出现在 plain_text 里，应当是 secret。不部署。`);
  }
  return REQUIRED_VARS.map(name => [name, vars.get(name)]);
}

/**
 * 部署后：新版本必须把同样的变量原样带上了。
 * 这一条正是 2026-08-12 那次事故唯一能提前抓到的地方。
 */
export function diffDeployedVars(expected, deployed) {
  const problems = [];
  for (const [name, value] of expected) {
    if (!deployed.has(name)) { problems.push(`${name} 丢失`); continue; }
    if (deployed.get(name) !== value) problems.push(`${name} 与部署前不一致`);
  }
  return problems;
}

/**
 * 部署后回读运行时，确认变量真的到了 worker 里，而不只是躺在配置上。
 * 只看部署身份这三个字段是否非空且与送进去的一致；
 * **不看上游账户服务健不健康** —— /readyz 实测会偶发 NOT_READY（约 1/13），
 * 上游抖一下就回滚好的部署是自己给自己挖坑。
 */
export function checkRuntimeIdentity(versionPayload, expectedVars) {
  const expected = new Map(expectedVars);
  const checks = [
    ["releaseCommit", "WRP_RELEASE_COMMIT"],
    ["ovhReleaseId", "WRP_OVH_RELEASE_ID"],
    ["edgeDeploymentId", "WRP_EDGE_DEPLOYMENT_ID"],
    ["taskpackVersion", "WRP_TASKPACK_VERSION"],
  ];
  const problems = [];
  for (const [field, varName] of checks) {
    const live = String(versionPayload?.[field] ?? "").trim();
    const want = String(expected.get(varName) ?? "").trim();
    if (!live) { problems.push(`运行时 ${field} 为空（${varName} 没到 worker 里）`); continue; }
    if (want && live !== want) problems.push(`运行时 ${field} 与送入的 ${varName} 不一致`);
  }
  return problems;
}

/** 任何要打印的文本都先过这里：变量值一律不许进日志。 */
export function redact(text, vars) {
  let output = String(text ?? "");
  for (const [name, value] of vars) {
    if (typeof value === "string" && value.length >= 4) {
      output = output.split(value).join(`<${name}>`);
    }
  }
  return output;
}
