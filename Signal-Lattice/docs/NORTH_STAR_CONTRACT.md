# 北极星不可拆分合同

每个 UTC 分钟只能形成一个 `cycle_id`。本轮链路必须按顺序完成：

1. 读取 MetaDatabase `Signal-Lattice/Stock_Skill/` Registry 与 AgentDatabase Serenity Skill；
2. 校验来源、版本、树 Hash、兼容合同和 Last-Known-Good；
3. 生成一次不可变市场快照；
4. 向所有 Active Skill 分发相同快照；
5. 每个 Skill 在独立子进程、独立临时目录和受限资源中执行，不可读取其他 Skill 输出；
6. 收集所有 Skill 的 PASS / ABSTAIN / FAILED 收据；
7. 中枢按证据根去重、保留正反冲突、使用历史可靠性权重进行协调；
8. 量化、时间、费用、流动性、容量、组合风险和证据门全部通过后，发布唯一建议；
9. 完整链路执行但硬门不通过时发布 `NO_ACTION`；链路不完整时发布 `SYSTEM_BLOCKED`；
10. 决策、Journal 和 Outbox 在同一事务中落账，网站和 Status 更新。

`Signal-Lattice/Stock_Skill/` 是受其自身 Registry 约束的动态 source-only 输入，不属于
Signal Lattice 程序发布物；每分钟必须从 GitHub 的该唯一规范路径重新协调并校验，不能以旧根目录回退。

任何一项被拆成未来版本，均视为北极星验收失败。
