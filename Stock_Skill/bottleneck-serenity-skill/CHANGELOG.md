# Changelog

## 0.0.0.1 — Stage 2 candidate activation

- 固定全局 stable ID、Skill basename、display name 与 invocation 为 `bottleneck-serenity-skill`，机器版本为
  `0.0.0.1`，展示/release label 为 `v0.0.0.1`。
- 建立 source-only 外层项目、53-entry 来源/迁移 ledger、Task Pack、canonical Skill 与确定性 UI metadata。
- 从用户提供的源包迁移五种研究模式、四道非补偿门、三个时钟、每股价值桥、独立证据/负向搜索、估值与
  capital-cycle red team、kill switches、几何/硬门评分、因果组合聚类和不可改写历史快照。
- 把源 README/quickstart 的产品与用法说明迁到外层 README；删除本机安装路径和复制命令，保持
  `SOURCE_ONLY / NOT_INSTALLED`。
- 把源 provenance/notice 迁到 `LICENSE_AND_ATTRIBUTION.md`，并对四个公开实现的完整 Git 历史做独立
  相似性审计；对与 `muxuuu/serenity-skill` 相似的有限 CLI/validator scaffolding 采取保守 MIT 归属。
- 增加 `RESTORE_AND_VERIFY.md`，明确当前 source 验证与后续 proposed-tree / clean-checkout sealed release
  重建边界。
- 实现标准库 deterministic builder：固定 ZIP root、UTF-8 byte order、1980 timestamp、`ZIP_STORED`、
  `0755/0644` mode、普通文件/type/file-set 门，并支持 build、activation 与完整 `--verify`。
- 从最终 Task Pack 连续双构建同一候选，以实算 SHA 激活 `SHA256SUMS`、registry 与 backup manifest release
  entry；backup manifest 最后生成，首版保持 `superseded_archives=[]` 且不创建伪 archive。
- 同步 root、`Stock_Skill` 与项目六个发现面。当前是 source-only registry entry 和 Stage 2 candidate release；
  首轮整体 Review 已发现 `S2-R001/S2-R002` 两个 P1 并 verdict `FAIL`，须先整改/重审，尚未 Publish、安装
  runtime，也没有 broker/order 能力。
- 增加无第三方依赖的 schema/example contract tests，以及 active release、确定性 ZIP、registry 与三 SHA 消费面
  的仓级耐久化回归；所有破坏性 fixture 均在临时副本运行，不改写 active artifacts。
- T002 对齐 Task Pack、项目 README 与 canonical integration 的 input/completion 精确 projection；统一运行期
  JSON/CSV artifact envelope，更新三份 schema、scaffold、示例和四个脚本输出，并加入缺字段、改名、错误
  version、过期 cutoff 与 overwrite 负向 Oracle。
- 新增标准库 full-history 许可相似性审计器、39-file hash-bound 报告与仓级 fixture/mutation tests；四个冻结
  upstream 的 2,485 个 eligible text blob instances 两次重算 byte-identical，exact=`0`、four-line pairs=`3`、
  token20 pairs=`1`，无明确许可仓 exact/token20 均为 `0`。两项 finding 仅推进为
  `FIXED_PENDING_REREVIEW`，等待 T003 独立重审，未执行 Publish。
- T003 用双实现冻结 47-file Task Pack 与 66-path Stage subject；四个 fresh full-history clone 的规范 Python
  报告 byte-identical，独立 Ruby 同得 39/2,489/2,485 与 exact/four-line/token20=`0/3/1`，因此
  `S2-R002` `CLOSED`。
- T003 同时证明 score/evidence/portfolio 三条 runtime 对缺失或改名 nullable `previous_version` 共 6/6
  fail-open；`S2-R001` 保持 `OPEN`、Stage verdict=`FAIL`。已追加 T004/T005 整改/重审对，当前仍未执行
  Publish、commit/push 或 runtime 安装。
- T004 在三条 runtime 中显式要求 `previous_version` key 存在；6/6 missing/rename 探针全部反转为非零，
  显式 `null` 与非空 lineage ID 正例保持通过。canonical suite 增至 22 cases；删除三处 presence 分支的
  临时回退 mutant 产生 6 failures。
- 六个 canonical target 改变后，以四个 fresh full-history clone 连续两次重算许可报告 byte-identical，
  39/2,489/2,485 与 exact/four-line/token20=`0/3/1` 不变。`S2-R001` 仅推进为
  `FIXED_PENDING_REREVIEW`，等待 T005 独立关闭；仍未执行 Publish、commit/push 或 runtime 安装。
- T005 以 Python/Ruby 双实现锁定 47-file Task Pack 与 66-path Stage source，记录 verdict 前复算无漂移；
  三条 runtime missing/rename 6/6 拒绝、`null`/lineage 6/6 通过，删除 presence 分支的回退 mutant 精确产生
  6 failures，因此 `S2-R001` `CLOSED`、`ACC-S2-013` PASS。
- 完整 Stage 2 重审同时复验 53-entry/43-9-1 来源、40 组核心行为、许可全历史、identity/version/UI、
  registry/release/hash DAG、96 tests、四个 workflow 原始 run blocks 与公开安全门；无新增 finding，ledger
  25/25 `CLOSED`，Stage verdict=`PASS`。下一 Task 是 P5 Publish；T005 未 commit/push 或安装 runtime。
- P5 的真实 clean sparse clone 暴露恢复命令在默认 cone-mode 下把 file operand 当作目录；命令已最小修正为
  显式 `--skip-checks`，并在隔离 clone 验证可精确物化声明 surface。该修正须在同一 P5 内重新封印，不提前
  声称最终 commit/push/CI 或 clean-checkout 验收完成。
