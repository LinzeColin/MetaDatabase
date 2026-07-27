# Task DAG

唯一机器 DAG 位于 `machine/task_dag.json`。ChatGPT 已完成实现和本地验证；Codex 只执行：只读核验目标基线 → 验证任务包 → 原样落库 → 运行目标 validator 和包内 Oracle → 失败则原样回滚并回报 → 成功后 commit/push/PR/merge/备份。

DAG 无真实时间 soak、等待节点、后台空转、重复审批或无限重试。任何不满足预条件的任务立即停止并输出事实、命令、退出码和日志；不得自行研究或改代码。

T-002/T-004 同时验证零本机足迹：封包不得含服务注册制品，目标仓 Oracle 必须运行 `verify_macos_zero_footprint.py`。不增加等待、soak 或后台观察节点。

T-004 同时运行业务基线矩阵 Oracle：验证五个纵向切片、阶段/状态/关系字段、无环依赖、矩阵 Hash、Status Endpoint 和宿主所有权。失败立即回滚，不新增等待节点。

同一 DAG 同时覆盖两个现有目标仓：MetaDatabase 落库 Skill/Registry；LinzeHomeHub 只应用 `status/collector/collect.py` 与 `status/web/index.html` 的冻结可逆补丁。任一仓失败时先回滚 Status，再回滚 Skill；全部通过后分别提交、合并、部署既有 Status 和备份。
