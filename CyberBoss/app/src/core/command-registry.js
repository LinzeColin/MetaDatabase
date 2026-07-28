const COMMAND_GROUPS = [
  {
    id: "lifecycle",
    label: "Lifecycle & Diagnostics",
    actions: [
      {
        action: "app.login",
        summary: "Start WeChat QR login and save the account",
        terminal: ["login"],
        weixin: [],
        status: "active",
      },
      {
        action: "app.accounts",
        summary: "List locally saved accounts",
        terminal: ["accounts"],
        weixin: [],
        status: "active",
      },
      {
        action: "app.start",
        summary: "Start the current channel/runtime main loop",
        terminal: ["start"],
        weixin: [],
        status: "active",
      },
      {
        action: "app.shared_start",
        summary: "Start the shared app-server and shared WeChat bridge",
        terminal: ["shared start"],
        weixin: [],
        status: "active",
      },
      {
        action: "app.shared_open",
        summary: "Attach to the shared thread currently bound in WeChat",
        terminal: ["shared open"],
        weixin: [],
        status: "active",
      },
      {
        action: "app.shared_status",
        summary: "Show the shared app-server and bridge status",
        terminal: ["shared status"],
        weixin: [],
        status: "active",
      },
      {
        action: "app.doctor",
        summary: "Print current config, boundaries, and thread state",
        terminal: ["doctor"],
        weixin: [],
        status: "active",
      },
      {
        action: "system.send",
        summary: "Write an invisible trigger message into the internal system queue",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "system.checkin_poller",
        summary: "Emit proactive check-in triggers at random intervals",
        terminal: [],
        weixin: [],
        status: "active",
      },
    ],
  },
  {
    id: "workspace",
    label: "Workspace & Thread",
    actions: [
      {
        action: "workspace.bind",
        summary: "Bind the current chat to an allowlisted workspace alias",
        terminal: [],
        weixin: ["/bind <workspace-alias>"],
        status: "active",
      },
      {
        action: "workspace.status",
        summary: "Show the current workspace, thread, model, and context usage",
        terminal: [],
        weixin: ["/status"],
        status: "active",
      },
      {
        action: "thread.new",
        summary: "Switch to a fresh thread draft",
        terminal: [],
        weixin: ["/new"],
        status: "active",
      },
      {
        action: "thread.reread",
        summary: "Make the current thread reread the latest instructions",
        terminal: [],
        weixin: ["/reread"],
        status: "active",
      },
      {
        action: "thread.compact",
        summary: "Compact the current thread context",
        terminal: [],
        weixin: ["/compact"],
        status: "active",
      },
      {
        action: "thread.switch",
        summary: "Switch to a specific thread",
        terminal: [],
        weixin: ["/switch <threadId>"],
        status: "active",
      },
      {
        action: "thread.stop",
        summary: "Stop the current run inside the thread",
        terminal: [],
        weixin: ["/stop"],
        status: "active",
      },
      {
        action: "system.checkin_range",
        summary: "Reset the proactive check-in range in minutes",
        terminal: [],
        weixin: ["/checkin <min>-<max>"],
        status: "active",
      },
      {
        action: "channel.chunk_min",
        summary: "Adjust the minimum short-chunk merge size for WeChat replies",
        terminal: [],
        weixin: ["/chunk <number>"],
        status: "active",
      },
    ],
  },
  {
    id: "approval",
    label: "Approvals & Control",
    actions: [
      {
        action: "approval.accept_once",
        summary: "Allow the current approval request once",
        terminal: [],
        weixin: ["/yes"],
        status: "active",
      },
      {
        action: "approval.accept_workspace",
        summary: "Keep allowing matching command prefixes in the current workspace",
        terminal: [],
        weixin: ["/always"],
        status: "active",
      },
      {
        action: "approval.reject_once",
        summary: "Deny the current approval request",
        terminal: [],
        weixin: ["/no"],
        status: "active",
      },
    ],
  },
  {
    id: "capabilities",
    label: "Capabilities",
    actions: [
      {
        action: "model.inspect",
        summary: "Inspect the current model",
        terminal: [],
        weixin: ["/model"],
        status: "active",
      },
      {
        action: "model.select",
        summary: "Switch to a specific model",
        terminal: [],
        weixin: ["/model <id>"],
        status: "active",
      },
      {
        action: "channel.send_file",
        summary: "Send a local file back to the current chat as an attachment",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "timeline.write",
        summary: "Write the current context into timeline",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "timeline.build",
        summary: "Build the static timeline site",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "timeline.serve",
        summary: "Start the static timeline site server",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "timeline.dev",
        summary: "Start the hot-reload timeline dev server",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "timeline.screenshot",
        summary: "Capture a timeline screenshot",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "reminder.create",
        summary: "Create a reminder and hand it to the scheduler",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "diary.append",
        summary: "Append a diary entry",
        terminal: [],
        weixin: [],
        status: "active",
      },
      {
        action: "app.star",
        summary: "Show fixed local source and compliance status",
        terminal: [],
        weixin: ["/star"],
        status: "active",
      },
      {
        action: "app.help",
        summary: "Show currently available commands for this channel",
        terminal: ["help"],
        weixin: ["/help"],
        status: "active",
      },
    ],
  },
];

function listCommandGroups() {
  return COMMAND_GROUPS.map((group) => ({
    ...group,
    actions: group.actions.map((action) => ({ ...action })),
  }));
}

// 终端帮助的第一屏必须回答一个问题：我现在该敲什么？所以只用一条命令开头，
// 其余的按"日常"和"排查"分开，进阶清单收到最后。
function buildTerminalHelpText() {
  const lines = [
    "",
    "CyberBoss —— 你的微信 AI 助手",
    "",
    "第一次用，只要这一条：",
    "",
    "    cyberboss",
    "",
    "  它会自动把该建的都建好，然后带你扫码登录。",
    "  装好之后再敲 cyberboss，就是直接启动。",
    "",
    "日常：",
    "  cyberboss           启动（第一次运行会先走安装向导）",
    "  cyberboss setup     重新走一遍安装向导",
    "  cyberboss login     重新扫码登录微信",
    "",
    "排查问题：",
    "  cyberboss doctor    看看现在的运行状况",
    "  cyberboss accounts  列出本机登录过的微信号",
    "",
    "启动之后，剩下的事都在微信里做：",
    "  给机器人发「帮助」——看看能做什么",
    "  发「邀请」——拿一串邀请码转发给朋友（只有主人可以）",
    "  发「状态」——看运行状况（只有主人可以）",
    "  发「设置」——打开设置页面填自己的 AI 密钥",
    "",
  ];

  const advanced = [];
  for (const group of COMMAND_GROUPS) {
    const activeActions = group.actions.filter((action) => action.status === "active" && action.terminal.length);
    if (!activeActions.length) {
      continue;
    }
    advanced.push(`- ${group.label}`);
    for (const action of activeActions) {
      advanced.push(`  ${formatTerminalExamples(action)}  ${action.summary}`);
    }
  }
  if (advanced.length) {
    lines.push("── 进阶（平时用不到）──", ...advanced, "");
  }
  lines.push("模型能用的能力以项目工具形式提供，不是终端子命令。");
  return lines.join("\n");
}

function buildWeixinHelpText() {
  const lines = ["💡 Available commands:"];
  for (const group of COMMAND_GROUPS) {
    const activeActions = group.actions.filter((action) => action.status === "active" && action.weixin.length);
    if (!activeActions.length) {
      continue;
    }
    lines.push("");
    lines.push(`${groupEmoji(group.id)} 【${group.label}】`);
    for (const action of activeActions) {
      lines.push(`  ${actionEmoji(action)} ${action.weixin.join(", ")} — ${action.summary}`);
    }
  }
  return lines.join("\n");
}

function groupEmoji(groupId) {
  switch (groupId) {
    case "lifecycle": return "🔄";
    case "workspace": return "📁";
    case "approval": return "🔐";
    case "capabilities": return "⚡️";
    default: return "•";
  }
}

function actionEmoji(action) {
  switch (action.action) {
    case "workspace.bind": return "📍";
    case "workspace.status": return "📊";
    case "thread.new": return "🆕";
    case "thread.reread": return "🔄";
    case "thread.compact": return "🗜️";
    case "thread.switch": return "🔀";
    case "thread.stop": return "⏹️";
    case "system.checkin_range": return "⏰";
    case "approval.accept_once": return "✅";
    case "approval.accept_workspace": return "💡";
    case "approval.reject_once": return "❌";
    case "model.inspect":
    case "model.select": return "🤖";
    case "app.help": return "❓";
    case "app.star": return "⭐️";
    default: return "•";
  }
}

module.exports = {
  buildTerminalHelpText,
  buildWeixinHelpText,
  listCommandGroups,
};

function formatTerminalExamples(action) {
  const terminal = Array.isArray(action?.terminal) ? action.terminal : [];
  if (!terminal.length) {
    return "";
  }
  return terminal.map((commandText) => toTerminalCommandExample(commandText)).join(", ");
}

function toTerminalCommandExample(commandText) {
  const normalized = typeof commandText === "string" ? commandText.trim() : "";
  switch (normalized) {
    case "login":
    case "accounts":
    case "start":
    case "doctor":
    case "help":
      return `cyberboss ${normalized}`;
    case "shared start":
    case "shared open":
    case "shared status":
      return `npm run ${normalized.replace(" ", ":")}`;
    case "start --checkin":
      return "cyberboss start --checkin";
    default:
      return normalized;
  }
}
