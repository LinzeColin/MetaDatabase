# 瓶颈分支一手证据卡：交接（第二轮收尾）

分支 `cloud/sl-bottleneck-cards-261001`。目标：给「结构性约束」里申报拿不到的八个因子建立可审计的证据卡机制并填入第一批真实卡片；门槛数字一个不动。
怎么做卡、怎么续期见 `重建/06_证据卡怎么做怎么续期.md`；起草细则见同目录 `bottleneck-cards-起草说明.md`（可直接交给起草人）。

## 一、完成情况

| 项 | 状态 |
|---|---|
| 卡片格式、解析、校验、读卡规则（`src/signal_lattice/evidence/cards.py`） | 完成，有 51 条测试（`tests/test_evidence_cards.py`） |
| 核验脚本 `scripts/verify_evidence_cards.py`、起草辅助 `card_getdoc.py`、`card_check.py` | 完成，已对 43 个真实来源跑过，全部 200 且摘录找到 |
| 接入瓶颈分支（`bottleneck.apply_cards`）、证据卡随快照钉住、`research --evidence-cards DIR` | 完成 |
| 随包发布（`pyproject.toml` package-data） | 完成，已实际 `pip wheel --no-deps --no-index` 验证 wheel 里有 5 张卡与 `verification.json` |
| 第一批卡片：5 张、21 家公司 | 完成（见下表） |
| 文档 `重建/06_...`、`HANDOFF.md` 条目 | 完成 |
| 完整 `signal-lattice research` 前后对比 | **未完成**：云端 `hq.sinajs.cn` 403，候选池无法重建。改做了 21 家公司的「无卡片 vs 有卡片」部分对比（PASS 0 → 0），见下 |
| 升版本号 | **没做**，见「三」 |

## 二、第一批卡片

| 卡 id | 公司（代码） | 评分的因子 |
|---|---|---|
| `nuclear-fuel-cycle` | UEC、UUUU、NNE、LEU、IMSR、URG | funded_demand 3、current_tightness 3、supplier_concentration 4、expansion_lead_time 2、policy_resilience 3 |
| `grid-equipment` | AMSC、PLPC、MYRG、CTRI、PRIM | current_tightness 2、supplier_concentration 3、expansion_lead_time 3 |
| `critical-minerals-antimony-rare-earths` | UAMY、PPTA、IDR、NB | funded_demand 2、current_tightness 3、supplier_concentration 4、substitution_difficulty 2、policy_resilience 2 |
| `sterile-injectables` | AMPH、ANIP、EBS | current_tightness 2、supplier_concentration 2 |
| `munitions-solid-rocket-motors` | KRMN、OLN、NPK | funded_demand 3、supplier_concentration 3 |

市值取自腾讯行情接口 2026-09-30（股价 × 股数，亿美元口径）；候选池正式口径以服务器上 `signal-lattice research` 建的快照为准，主线用新快照复核一遍再采信。
卡片里没有 `qualification_barrier`、`architectural_necessity`：没找到够格的一手证据，按规则不写。

## 三、给主线的待办

1. **升版本号**：`deploy_v2.sh` 对同版本、不同 wheel 会 `VERSION_COLLISION` 退出。本分支没升（并行分支也在改 Signal-Lattice，避免冲突）。合并后按 `HANDOFF.md` 里 0.0.0.3.4 那条的做法，`pyproject.toml`、`openapi.yaml`、`config/default.json`、`machine/facts/*.json` 同步升。
2. **完整研究层前后对比**（服务器上跑）：
   ```
   export SIGNAL_LATTICE_SEC_UA="SignalLattice research <联系邮箱>"
   # 基线：空卡片目录
   mkdir -p /tmp/empty-cards
   signal-lattice research --work-dir <W> --out-dir <O1> --evidence-cards /tmp/empty-cards
   # 带卡片（默认读包内目录），沿用同一个 work-dir，跳过采集
   signal-lattice research --work-dir <W> --out-dir <O2> --skip-collect
   ```
   比较两份瓶颈分支收据的 PASS 数，读 `detail.evidence_cards.used` 与 `detail.gates`。
3. **拍板：要不要只登记供给方**。NNE、IMSR（反应堆开发商）、MYRG/CTRI/PRIM（施工承包商）是瓶颈的使用方，卡片以 `PROXY` 套给它们后门 A 会过；它们后续在资本获取能力（`pricing_power`）上过不了，但语义上是否合适需要主线决定。
4. **到期提醒**：`current_tightness`/`funded_demand` 2027-03-31 到期，整卡 2027-09-30。续期步骤见 06 文档第 6 节。

## 四、部分前后对比（21 家，截至 2026-09-30，无 10-K 正文抽取、无同业对照）

PASS：0 → 0。约束维度覆盖率 0.25（多数）→ 0.35–0.60。门 A（约束真实，≥60 且覆盖率 ≥0.40）：IMSR、NNE 过（60.0）；KRMN、ANIP 分数够但覆盖率 <0.40 未验证；
IDR 58.3、MYRG 55.6、NB/PPTA 50.0 分数不够。其余公司被门 C（`pricing_power`/`unit_economics` 无证据或分数不够）、门 D（`valuation_asymmetry` 无证据）挡住。
注意卡片也会拉低分数（IDR 68 → 58.3、ANIP 60 → 48.6、KRMN 72 → 68.6）：低评分的卡片因子取代了「没证据」，这是设计内行为。

## 五、怎么在本机复核

```
cd Signal-Lattice
PYTHONPATH=src:tests python -m pytest -q tests                                   # 全量 745 条
PYTHONPATH=src python scripts/card_check.py src/signal_lattice/evidence_cards    # 结构 + 印章
SIGNAL_LATTICE_SEC_UA="SignalLattice research <邮箱>" PYTHONPATH=src python scripts/verify_evidence_cards.py   # 联网重新核验全部来源
```

## 六、踩过的坑

- 云端沙箱：`www.sec.gov` / `data.sec.gov` 带 UA 可用，`efts.sec.gov` 与 `hq.sinajs.cn` 403；army.mil、congress.gov 部分页面对自动请求 403（这些来源没写进卡片）。
- 摘录里的 `U.S.` 会被句子计数当句末，摘录超 2 句就被判不合格。
- `basis` 至少 10 个字。
- 在 worktree 里的 shell 对「复合命令 + 运行时计算的路径」有限制，长脚本写成文件再运行。
- 候选池 CIK：LEU（Centrus）现在市值 28.5 亿在区间内，上一轮交接说它超区间，已过时。
