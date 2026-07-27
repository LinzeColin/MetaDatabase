import {
  APP_NAME,
  APP_VERSION,
  CHATGPT_HANDOFF_URL,
  OFFICIAL_WEREAD_SKILL_URL,
  OPERATIONS_STATUS_URL,
  SOURCE_REPOSITORY_URL,
  SUPPORT_ISSUES_URL,
} from "./constants.js";
import { businessLineDefinitions, stateLabel } from "./business-governance.js";

export const LEGAL_EFFECTIVE_DATE = "2026-07-27";

const PRIVACY_SECTIONS = Object.freeze([
  {
    title: "适用范围与维护者",
    body: [
      `${APP_NAME}是一个公开、匿名使用的个人阅读笔记迁移工具，由 ${SOURCE_REPOSITORY_URL} 对应项目的维护者提供和维护。它不是腾讯、微信读书或 OpenAI 的官方产品，也不代表这些平台作出授权、背书或保证。`,
      `本政策适用于本站的浏览器界面、ChatGPT Sites 同源薄代理、本地便携预览和项目自运行运维面。维护问题可通过项目公开问题入口提交；报告安全问题时不得在公开页面粘贴密钥、笔记或其他敏感内容。`,
    ],
  },
  {
    title: "我们处理哪些数据",
    body: [
      "使用演示数据时，不需要你的微信读书密钥或个人笔记。",
      "使用本地上传时，你主动选择的 ZIP、JSON、Markdown 或 TXT 文件只在当前浏览器的隔离任务内读取、校验和整理。",
      "连接微信读书时，浏览器会把你本人提供的微信读书密钥和经过白名单约束的请求，经本站同源薄代理转发到腾讯官方微信读书智能接口网关；上游响应会短暂经过托管运行时，再返回当前浏览器会话。",
      "本站会处理完成导出所必需的书名、章节、个人划线、想法、点评、阅读进度和统计字段，但不把这些内容写入应用数据库、OVH 运行日志、Private-Database、R2、OCI 或分析事件。",
    ],
  },
  {
    title: "处理目的与处理位置",
    body: [
      "数据只用于预览可导出范围、生成中文 Markdown、Canonical JSON、离线搜索页、迁移 ZIP，以及生成一份由你主动上传到 ChatGPT 的阅读笔记文件。",
      "本地文件解析、规范化、格式渲染、压缩和下载均在当前浏览器完成。连接微信读书时，密钥和上游响应会在浏览器、ChatGPT Sites 托管运行时与腾讯官方接口之间短暂传输；本站不承诺这些平台具有特定数据驻留地区。",
    ],
  },
  {
    title: "保存、清除与备份边界",
    body: [
      "本站不主动在服务器端持久化微信读书密钥、上传文件、原始接口响应、笔记正文、搜索词、ChatGPT 提问词或生成的 ZIP。",
      "浏览器当前会话会在你点击“断开并清除当前会话”、关闭页面或连续 15 分钟无操作后清除隔离任务中的敏感状态；下载到你设备中的文件由你自行管理。",
      "OVH、Private-Database、R2 和 OCI 只保存脱敏的发布、故障、恢复、备份对象引用、哈希和运行摘要，不保存用户笔记或密钥。",
    ],
  },
  {
    title: "访问统计、日志与第三方",
    body: [
      "ChatGPT Sites 可能提供站点级独立访客和页面浏览量统计。应用不会主动把密钥、书名、文件名、搜索词、笔记或下载内容发送给统计系统。",
      "完成一次真实微信读书连接会涉及腾讯官方微信读书接口；托管和页面交付会涉及 ChatGPT Sites。点击“打开 ChatGPT”会前往固定官方入口，但本站不会把密钥、笔记或提问词附加到跳转网址。",
      "站点不会加载第三方广告、外部字体、库存图片或跨站跟踪脚本。",
    ],
  },
  {
    title: "你的选择与责任",
    body: [
      "你可以只使用演示数据或本地文件而不连接微信读书；可以随时断开并清除当前会话；也可以不打开 ChatGPT。",
      "请只处理自己有权访问的个人数据，并妥善保管密钥和下载文件。不要把真实密钥或敏感笔记提交到公开问题、聊天记录、截图或日志。",
      `关于公开代码、隐私说明或删除边界的问题，可访问 ${SUPPORT_ISSUES_URL}。本工具没有账户数据库，因此不存在由本站维护的账户资料可供导出或删除。`,
    ],
  },
  {
    title: "安全、儿童与政策变更",
    body: [
      "系统使用同源请求、接口与参数白名单、请求和响应大小上限、有限重试、无缓存响应、安全响应头和敏感信息扫描来降低风险；任何系统仍可能存在未知缺陷。",
      "本服务不以儿童为目标，也不要求提交身份证件、支付信息、健康信息或其他与阅读笔记迁移无关的敏感信息。",
      `本政策生效日期为 ${LEGAL_EFFECTIVE_DATE}。重要变更会随代码版本和发布记录更新；本页不是对任何司法辖区合规认证的声明。`,
    ],
  },
]);

const TERMS_SECTIONS = Object.freeze([
  {
    title: "服务目的与适用范围",
    body: [
      `${APP_NAME}用于把使用者本人有权访问的微信读书个人笔记或本地阅读笔记，整理为可下载、可校验和可继续使用的文件。服务按现状提供，当前 P0 不提供账户、服务器端笔记库、个人定时同步、整书下载或模型推理。`,
      "使用本站即表示你理解其非官方性质，并同意遵守微信读书、ChatGPT、GitHub 和所在地区适用的强制性规则。",
    ],
  },
  {
    title: "允许用途",
    body: [
      "迁移、备份、整理和检索你本人有权访问的阅读笔记；把由本站生成的文件主动添加到你自己的 ChatGPT 会话或项目；在自己控制的设备和知识工具中继续使用导出结果。",
    ],
  },
  {
    title: "禁止用途",
    list: [
      "收集、共享、猜测、买卖或滥用他人的微信读书密钥或账户访问权。",
      "抓取、破解、导出或分发整本受版权保护的书籍、付费内容或你无权使用的资料。",
      "上传恶意归档、路径穿越文件、超大压缩炸弹，或以自动化方式规避限流、干扰服务或上游平台。",
      "把本站、OpenAI、腾讯或微信读书描述为已审核、保存、担保或认可你的笔记和导出内容。",
      "绕过安全停止、升级提示、权限边界或数据完整性检查。",
    ],
  },
  {
    title: "密钥、文件与内容责任",
    body: [
      "微信读书密钥与使用者身份绑定，应由你本人从官方能力获得并只在当前会话使用。本站不提供共享密钥。",
      "你应核对导出报告、文件清单、成功与失败数量和 SHA-256。标记为“部分结果”的文件不是完整备份；上传文件的合法性、准确性和保管责任由你承担。",
    ],
  },
  {
    title: "可用性、上游变化与安全停止",
    body: [
      `微信读书接口、ChatGPT Sites、网络和浏览器能力可能变化。收到官方升级指令、密钥失败、上游结构变化、文件完整性失败或不可逆冲突时，系统会停止受影响操作，而不是生成看似成功的空结果。官方能力说明以 ${OFFICIAL_WEREAD_SKILL_URL} 为准。`,
      "7×24 是架构、监控、自愈、备份和恢复目标，不表示当前已经通过连续运行 N 小时证明生产级可用性。",
    ],
  },
  {
    title: "责任限制与变更",
    body: [
      "在适用法律允许的范围内，维护者不对上游中断、浏览器或网络故障、使用者误操作、未经核对的部分导出、第三方平台规则变化或使用者自行上传到其他服务后的处理结果作超出实际控制范围的保证。",
      `服务可以为安全、平台规则、成本或维护需要调整或停止受影响能力。变更会通过版本、代码和发布记录体现。问题入口为 ${SUPPORT_ISSUES_URL}，运行概览见 ${OPERATIONS_STATUS_URL}。`,
    ],
  },
]);

export function legalTitle(kind) {
  return kind === "privacy" ? "隐私政策" : "使用条款";
}

export function legalKicker(kind) {
  return kind === "privacy" ? "数据如何被处理" : "使用权利与责任";
}

export function legalSections(kind) {
  return kind === "privacy" ? PRIVACY_SECTIONS : TERMS_SECTIONS;
}

export function legalContentHtml(kind) {
  return legalSections(kind).map(section => {
    const body = (section.body ?? []).map(paragraph => `<p>${linkify(paragraph)}</p>`).join("");
    const list = section.list ? `<ul>${section.list.map(item => `<li>${linkify(item)}</li>`).join("")}</ul>` : "";
    return `<section class="legal-section"><h2>${escapeHtml(section.title)}</h2>${body}${list}</section>`;
  }).join("");
}

export function legalMainHtml(kind) {
  return `<a class="skip-link" href="#legal-content">跳到正文</a>${siteHeaderHtml()}<main class="legal" id="legal-content"><p class="section-label">${legalKicker(kind)}</p><h1>${legalTitle(kind)}</h1><p class="legal-summary">请先阅读与自身使用方式相关的处理边界。核心原则是：不提供共享密钥、不主动持久化用户笔记、失败不伪装成功。</p>${legalContentHtml(kind)}<div class="legal-contact"><h2>联系与版本</h2><p>项目问题入口：<a href="${SUPPORT_ISSUES_URL}" rel="noreferrer">MetaDatabase 公开问题</a>。报告安全问题时请勿公开粘贴密钥或笔记。</p><p>版本 ${APP_VERSION} · 生效日期 ${LEGAL_EFFECTIVE_DATE}</p></div></main>${siteFooterHtml()}`;
}

export function statusMainHtml() {
  return `<a class="skip-link" href="#status-content">跳到系统状态</a>${siteHeaderHtml()}<main class="status-page" id="status-content"><p class="section-label">公开运行状态</p><h1>系统状态</h1><p class="status-intro">本页区分页面存活、静态资源就绪、微信读书代理合同和外部运维概览，并用业务基线矩阵展示每条纵向链路的阶段、状态、依赖、证据与恢复动作。它不使用你的微信读书密钥进行探测，也不展示任何用户内容。</p><div id="status-overview" class="status-overview" aria-live="polite"><article class="status-hero neutral"><span class="status-large-dot" aria-hidden="true"></span><div><p class="outcome-label">正在读取</p><h2>正在获取当前运行状态</h2><p>如果 JavaScript 被禁用，仍可直接访问机器接口 <a href="/healthz">/healthz</a>、<a href="/readyz">/readyz</a> 和 <a href="/api/status">/api/status</a>。</p></div></article></div><div id="status-components" class="status-components"><article><h2>公开应用</h2><p>等待运行时检查。</p></article><article><h2>微信读书代理</h2><p>只检查代理合同是否可用，不使用任何用户密钥调用上游。</p></article><article><h2>数据处理边界</h2><p>用户密钥、笔记和下载文件不进入运维状态。</p></article></div>${businessGovernanceStaticHtml()}<section class="status-links"><h2>更多运行信息</h2><p><a href="${OPERATIONS_STATUS_URL}" rel="noreferrer">打开供应商与基础设施状态入口</a></p><p class="microcopy">外部状态入口与本产品状态页职责不同：前者展示供应商资源，本站页面展示当前应用可观察能力。业务矩阵中的“尚未实证”不等于故障，而是明确表示当前状态检查没有使用用户密钥或私有基础设施凭据。</p></section><noscript><p class="status-noscript">浏览器已禁用 JavaScript，因此无法自动刷新人类可读状态；下方静态业务矩阵仍可阅读，机器接口也可直接打开。</p></noscript></main>${siteFooterHtml()}`;
}

export function businessGovernanceStaticHtml() {
  const rows = businessLineDefinitions().map(line => `<tr data-business-line="${escapeAttr(line.id)}"><th scope="row"><strong>${escapeHtml(line.name)}</strong><span>${escapeHtml(line.id)}</span></th><td>${escapeHtml(line.phase)}</td><td><span class="business-state not-verified">${stateLabel("NOT_VERIFIED")}</span></td><td>${escapeHtml(dependencyText(line))}</td><td>${escapeHtml(line.oracle)}</td><td>等待运行时证据；无需 JavaScript 也可核对业务边界。</td></tr>`).join("");
  return `<section class="business-governance" aria-labelledby="business-governance-title"><div class="business-governance-heading"><div><p class="section-label">业务基线纵向切片</p><h2 id="business-governance-title">端到端白箱治理矩阵</h2></div><p id="business-governance-summary" class="microcopy">静态合同已加载；动态状态等待 /api/status。</p></div><div class="business-table-wrap"><table><thead><tr><th scope="col">业务线</th><th scope="col">阶段</th><th scope="col">状态</th><th scope="col">依赖与耦合</th><th scope="col">验收 Oracle</th><th scope="col">恢复或下一步</th></tr></thead><tbody id="business-governance-body">${rows}</tbody></table></div></section>`;
}

function dependencyText(line) {
  const all = line.dependsOnAll.length ? `全部：${line.dependsOnAll.join("、")}` : "无强制前置";
  const any = line.dependsOnAny.length ? `；任一：${line.dependsOnAny.join("、")}` : "";
  return `${all}${any}`;
}

export function standaloneDocument({ title, description, body }) {
  return `<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n<meta name="theme-color" content="#f7faf9" media="(prefers-color-scheme: light)" />\n<meta name="theme-color" content="#0d1411" media="(prefers-color-scheme: dark)" />\n<meta name="color-scheme" content="light dark" />\n<meta name="description" content="${escapeAttr(description)}" />\n<link rel="manifest" href="/manifest.webmanifest" />\n<link rel="stylesheet" href="/src/ui/styles.css" />\n<title>${escapeHtml(title)}</title>\n</head>\n<body>\n<div id="app">${body}</div>\n<script type="module" src="/src/ui/app.js"></script>\n</body>\n</html>\n`;
}

export function siteHeaderHtml() {
  return `<header class="topbar"><a class="brand" href="/" aria-label="${APP_NAME}首页"><span class="brand-mark" aria-hidden="true">阅</span><span class="brand-copy"><strong>${APP_NAME}</strong><small>上传、整理、下载并继续询问</small></span></a><div class="header-trust" aria-label="隐私状态"><span class="status-dot" aria-hidden="true"></span>密钥、上传文件与笔记默认不落库</div><nav aria-label="站点导航"><a href="/">迁移工具</a><a href="/privacy/">隐私</a><a href="/terms/">条款</a><a href="/status/">系统状态</a></nav></header>`;
}

export function siteFooterHtml() {
  return `<footer><div class="footer-brand"><strong>${APP_NAME}</strong><span>非微信读书或 OpenAI 官方产品</span></div><p>只处理使用者本人授权的数据；真实微信读书连接经同源薄代理短暂处理，应用不主动持久化密钥或笔记。</p><div class="footer-links"><a href="/privacy/">隐私政策</a><a href="/terms/">使用条款</a><a href="/status/">系统状态</a><a href="${SOURCE_REPOSITORY_URL}" rel="noreferrer">源代码</a></div></footer>`;
}

function linkify(value) {
  const source = String(value ?? "");
  const pattern = /https:\/\/[A-Za-z0-9._~:/?#[\]@!$&'()*+,;=%-]+/gu;
  let output = "";
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    const start = match.index ?? 0;
    const raw = match[0];
    const trailing = raw.match(/[.,;:!?]+$/u)?.[0] ?? "";
    const url = trailing ? raw.slice(0, -trailing.length) : raw;
    output += escapeHtml(source.slice(cursor, start));
    output += `<a href="${escapeAttr(url)}" rel="noreferrer">${escapeHtml(shortLinkLabel(url))}</a>${escapeHtml(trailing)}`;
    cursor = start + raw.length;
  }
  return output + escapeHtml(source.slice(cursor));
}


function shortLinkLabel(value) {
  try {
    const url = new URL(value);
    if (url.hostname === "github.com") return "GitHub 项目入口";
    if (url.hostname === "status.linzezhang.com") return "运行状态入口";
    return url.hostname;
  } catch {
    return value;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/gu, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/gu, "&#96;");
}
