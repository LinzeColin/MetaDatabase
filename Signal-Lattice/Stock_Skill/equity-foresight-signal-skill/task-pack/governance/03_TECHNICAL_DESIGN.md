# 技术设计

三平面：Skill Contract Plane；Deterministic Runtime Plane；Evidence & Validation Plane。

关键接口：`prepare_bundle`、`evaluate_prepared`、`prepare_suite`、`evaluate_suite`、`train_direction_pipeline`、`health_snapshot`、`compare_candidate_to_lkg`、`build_host_status_payload`、`build_recovery_plan`。

Canonical JSON + SHA-256；拒绝 Pickle/Joblib/动态 import/远程模型；有界文件、节点、专家、桶和批量；无网络/Secret/数据库/daemon；seccomp 阻断 socket 与子进程；Linux user+network namespace 验证离线运行。错误路径输出 `ABSTAIN` 或受控错误，不使用 LLM fallback。

只读比较 Candidate/LKG，自动晋级永久禁止；宿主显式应用和回滚。Skill 不写长期状态。时间逻辑使用显式 `as_of`、Fixture 和历史回放，无真实时间 soak。

零本机足迹由两层证明：静态扫描拒绝 `.plist/.service/.timer/.socket`、launchd 入口、HOME/XDG 持久化 API；动态 Oracle 将 HOME/XDG/TMP/PYTHONPYCACHEPREFIX 重定向到隔离目录，以 `-B` 运行 self-check、推断和训练，之后要求新增/变更文件、持久字节和遗留进程全部为 0。该 Oracle 证明“调用后零持久/零常驻”，不伪称“执行瞬间零 CPU/RAM”。

## 业务基线矩阵

Status Adapter 生成 `efs.business_baseline_matrix.v1`，固定五个纵向切片：输入控制、Shadow 预测、Outcome 证伪、Candidate/LKG 生命周期、Status/恢复。矩阵与 Host Status Payload 双 Hash 绑定；边集合必须无环且全部节点可解析。耦合只通过显式 Hash、状态和依赖关系表达，不允许隐式跨模块共享状态。

Status 接入面位于任务包外层 `status_integration/`：锚点预检 → 原子补丁 → Python/JavaScript 语法验证 → 可逆回滚。宿主 writer 校验 Host Payload 与 Matrix 双 Hash 后原子写入既有 OVH status data 目录；采集器二次校验并 fail closed。该适配层不是第二控制面。
