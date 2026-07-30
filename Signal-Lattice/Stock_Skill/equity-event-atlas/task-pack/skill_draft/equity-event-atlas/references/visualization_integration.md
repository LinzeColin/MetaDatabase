# 可视化与现有系统接入

## 1. 固定制品

| 文件 | 用途 |
|---|---|
| `REPORT.md` | 中文结论、事件、情景、动作、证据与限制 |
| `event_timeline.mmd` | 事件时间轴 |
| `event_graph.mmd` | 事件依赖、放大、抵消与冲突图 |
| `scenario_fan.svg` | Bear/Base/Bull 区间扇形图 |
| `supply_waterfall.svg` | 潜在供应增减瀑布图 |
| `STATUS_FRAGMENT.json` | 宿主状态页可消费的状态片段 |
| `render_manifest.json` | 派生制品路径、大小和 SHA-256 |

## 2. UI 顺序

宿主页面建议采用渐进披露：

```text
结论与能力门
→ 最近三项关键事件
→ 情景概率与动作阶梯
→ 时间线和图表
→ 声明与证据
→ 方法、限制和校准
```

第一屏必须让用户看见：当前能力、结论、最大风险、下一节点和是否允许动作。不要让图表遮蔽证据不足。

## 3. 嵌入规则

- Markdown：用于 GitHub、Notion、Obsidian 或报告管线。
- Mermaid：由宿主已有渲染器处理；没有渲染器时仍可显示源文本。
- SVG：可直接嵌入网页或转为 PNG/PDF；无需 JavaScript。
- JSON：作为前端、搜索、状态和其他 Skill 的稳定接口。

## 4. 可访问性

- SVG 包含 title 与 desc。
- 不只使用颜色表达情景；同时显示标签、概率和线型。
- 报告表格提供与图形相同的核心数值。
- 长事件标题在 UI 截断时，完整文本仍保留在 JSON 与报告。

## 5. 禁止

- 不在 Skill 内自建前端、登录、数据库或长期进程。
- 不把派生 SVG 或 Markdown写成第二权威事实源。
- 不让用户从图形直接触发交易。
- 不用动画或视觉强调掩盖 `RESEARCH_ONLY`、`BLOCKED` 或低置信度。
