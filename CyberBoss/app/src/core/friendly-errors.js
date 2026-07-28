"use strict";

// 把内部错误码翻译成"发生了什么 + 现在该做什么"。
//
// 规则：每条都必须给出可执行的下一步。没有匹配到的错误不会被伪装成已知问题，
// 而是照实说"没见过这个问题"并把原始信息留在下面，因为编一个听起来合理的
// 解释比直接显示错误码更糟。

const KNOWN = Object.freeze([
  {
    match: /workspace_config_unavailable|workspace_config_not_file|workspace_config_invalid_json|workspace_config_schema|workspace_config_empty/,
    title: "工作目录的配置还没准备好",
    next: "运行一次：cyberboss setup（它会自动生成，不用你手写）",
  },
  {
    match: /workspace_root_unavailable|workspace_root_not_directory/,
    title: "工作目录不见了",
    next: "运行一次：cyberboss setup，它会重新建好这个目录",
  },
  {
    match: /workspace_entry_outside_base|workspace_root_escape|workspace_base_/,
    title: "工作目录被指到了不该去的地方",
    next: "删掉数据目录里的 workspaces.json，再运行：cyberboss setup",
  },
  {
    match: /RUNTIME_ENCRYPTION_KEY_UNAVAILABLE|RUNTIME_IDENTITY_KEY_UNAVAILABLE|KEY_FILE_INVALID/,
    title: "密钥文件缺失",
    next: "运行一次：cyberboss setup，它会生成密钥（首次安装才会生成）",
  },
  {
    match: /RUNTIME_ENCRYPTION_KEY_PERMISSIONS_INVALID|RUNTIME_IDENTITY_KEY_PERMISSIONS_INVALID/,
    title: "密钥文件的权限太松了，别人也能读",
    next: "运行一次：cyberboss setup，它会自动把权限收紧",
  },
  {
    match: /KEY_FILE_LENGTH_INVALID|_LENGTH_INVALID/,
    title: "密钥文件的内容不对",
    next: "把数据目录里 credentials 文件夹整个删掉再运行 cyberboss setup。注意：这会让已注册的用户需要重新开通",
  },
  {
    // 这条真实文案是 "No saved WeChat account was found. Run `npm run login`
    // first." —— 里面的 npm 指令对终端用户是错的，所以整条替换掉。
    match: /no saved wechat account|ACCOUNT_NOT_FOUND|account_not_found|resolveAccount|npm run login/i,
    title: "还没有登录微信",
    next: "运行一次：cyberboss login，然后用要当机器人的那个微信扫码",
  },
  {
    match: /SESSION_EXPIRED|errcode.*-14|session expired/i,
    title: "微信登录过期了",
    next: "重新扫一次码：cyberboss login",
  },
  {
    match: /ENOTFOUND|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN/,
    title: "连不上网络",
    next: "检查一下网络，然后重新运行刚才那条命令",
  },
  {
    match: /EACCES|EPERM/,
    title: "没有权限读写文件",
    next: "确认数据目录属于当前用户；不要用 sudo 运行 CyberBoss",
  },
  {
    match: /ENOSPC/,
    title: "磁盘满了",
    next: "清理一些空间再启动",
  },
  {
    match: /CB_PORTAL_ORIGIN/,
    title: "设置页面的网址填得不对",
    next: "网址要长这样：https://你的域名（https 开头、结尾不带斜杠）。改完重新运行，或者运行 cyberboss setup 重新填",
  },
  {
    match: /CB_REGISTRATION_MODE/,
    title: "开通方式只能是邀请制或开放",
    next: "运行 cyberboss setup 重新选一次",
  },
  {
    match: /DURABLE_INBOX|JOB_SCHEDULER|DURABLE_OUTBOX|CANONICAL_SYNC_POLICY/,
    title: "有一项内部开关被改成了不允许的值",
    next: "把数据目录里 .env 中以 CB_ 开头的那几行删掉，再运行：cyberboss setup",
  },
]);

const UNKNOWN_TITLE = "遇到了一个没见过的问题";
const UNKNOWN_NEXT = "先运行 cyberboss doctor 看看状态。如果要报告这个问题，请把下面这行原始信息一起附上";

// 返回给用户看的多行文本。原始错误始终保留在最后一行，既不丢信息，也不用
// 让用户先读懂它。
function explainError(error) {
  const raw = error instanceof Error
    ? (error.code ? `${error.code}: ${error.message}` : error.message)
    : String(error ?? "");
  const known = KNOWN.find((entry) => entry.match.test(raw));
  const lines = [
    "",
    `✗ ${known ? known.title : UNKNOWN_TITLE}`,
    "",
    `  怎么办：${known ? known.next : UNKNOWN_NEXT}`,
  ];
  if (!known) {
    lines.push("", `  原始信息：${raw}`);
  } else {
    lines.push("", `  （技术细节：${raw}）`);
  }
  lines.push("");
  return lines.join("\n");
}

module.exports = { KNOWN, explainError };
