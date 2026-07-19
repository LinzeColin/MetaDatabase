# 验收清单

状态只允许 `PASS / FAIL / BLOCKED / NOT_RUN / NOT_AVAILABLE`。没有同次证据不得标 PASS。

## A. 定位

- [ ] 目录与 frontmatter 均为 `stock-commercial-opportunities`。
- [ ] 中文显示名为“股票商业机会拆解”。
- [ ] 只处理 listed-equity research triage，不处理私人商业机会/信用/个人财务建议。
- [ ] `SCREEN / ATTRIBUTE / UNDERWRITE` 有 cap、输入、退出和停止。
- [ ] 本地安装明确 `NOT_RUN`，两个全局 Skill 根无新 ID。

## B. 商业到股票链

- [ ] payer/budget/value pool/bottleneck/cost bearer/substitute 可分辨。
- [ ] beneficiary、supplier、enabler、substitute、laggard、false positive 可区分。
- [ ] issuer/ticker/exchange/share class/security/currency/as-of 先核验。
- [ ] product/segment/geography exposure 有 denominator/period/units。
- [ ] orders/backlog/revenue/margin/cash-flow capture 不由 TAM 推断。
- [ ] expectations verified/inferred 分开；valuation/provider/timestamp 明确。
- [ ] catalyst 有日期来源和 revision path；first rejection/falsifier 可执行。

## C. Evidence / scoring / status

- [ ] Fact/Inference/Estimate/Opinion/Unverified 分开。
- [ ] 核心 claim 有已打开 source IDs；所有 URL 已登记。
- [ ] snippet/social/synthetic-only 不能支持 core fact/estimate。
- [ ] score、risk deduction、confidence、E0–E5 独立。
- [ ] E0/E1 不高于 SCREEN_FLAG；E2+ 才可 DILIGENCE_NEXT；E4+ 才可 ADVANCE_RESEARCH。
- [ ] hard stop 覆盖分数；未知/过期字段导致降级。
- [ ] 允许 `NO_QUALIFIED_CANDIDATE`，不强填 Top N。

## D. Diligence

- [ ] 每个 card 只绑定一个 critical claim/assumption。
- [ ] source category、field、period、denominator、timestamp 明确。
- [ ] pass/fail/inconclusive 在执行前预注册且会改变决定。
- [ ] time/data/coordination cap、owner、review date 明确。
- [ ] 无证据的 completed result 被阻断。
- [ ] 默认只给一个最高 VOI next workflow。

## E. 金融安全/许可

- [ ] 输出声明 research prioritization—not investment advice。
- [ ] 无个性化 buy/sell/hold、仓位、自动交易、目标价或收益保证。
- [ ] 无 portfolio/account/transaction/customer/credential/local-session/MNPI。
- [ ] public + private raw source 被阻断；synthetic fixture 明标。
- [ ] 当前法规、价格、估值、consensus、事件同次核验或标 unknown/stale。
- [ ] 付费墙/账号/robots/access control 不绕过；受限数据不再分发。
- [ ] 社交荐股、price momentum 和 AI persona 只作 lead。

## F. 确定性验证

- [ ] `validate_skill.py --strict`：0 error / 0 warning。
- [ ] `validate_deliverable.py --strict`：0 error / 0 warning。
- [ ] scorer fixture：S001=E5/ADVANCE_RESEARCH；S002=E3/DILIGENCE_NEXT；S003=E0/REJECT。
- [ ] 单元/CLI suite：至少 29 tests 全 PASS。
- [ ] 2 JSON、2 JSONL、1 CSV 和 YAML 均可解析。
- [ ] trigger=22（12 正/10 负）；quality=8。
- [ ] Python imports 仅标准库；无 cache/temp/log/secret/local-user-path。
- [ ] Markdown 相对链接存在且不逃逸。
- [ ] 当前官方 Skill validator PASS，或如实 `NOT_AVAILABLE/NOT_RUN`。

## G. 发布与恢复

- [ ] task-pack `MANIFEST.sha256` 重算通过。
- [ ] v3 ZIP `unzip -t` 通过且无父目录逃逸/绝对路径/symlink。
- [ ] 解压副本重复 F 项阻断检查。
- [ ] root `BACKUP_MANIFEST.sha256` 覆盖 task-pack/release/archives。
- [ ] v1/v2 archive SHA 与 `SOURCE_INVENTORY.md` 一致。
- [ ] GitHub `main` 独立 sparse clone/download 后重复 hash/restore。

## H. 语义评估

- [ ] 12 positive recall ≥90%，10 negative specificity ≥90%。
- [ ] Q01/Q04/Q05/Q08 完成 paired A/B 与盲评。
- [ ] exposure、capture、evidence、calibration 至少 3 项提升 ≥1。
- [ ] 无安全退化、虚构 current data、强填候选或成本无理由 >2.5x。

未运行 H 时只能交付“source package deterministic PASS”，不能声称真实模型效果。

## 阻断失败

伪造证券/来源/current data；theme 冒充 exposure；分数绕过 E-level；私密/付费数据/MNPI 泄漏；个人交易指令；未授权外部动作；测试/manifest/restore 失败却写 PASS；覆盖历史 archive；远端未可恢复即删除唯一 local source。
