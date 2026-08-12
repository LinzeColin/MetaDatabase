# 需求与验收追踪

| 需求 | 不变量 | 验收 | 业务 Oracle | 主要测试／证据 |
|---|---|---|---|---|
| 金融硬资格 | INV-QUALIFICATION-012 | AC-FINANCE-02 | 十五年经验金融总监对 Early Career 用户必须不符合 | `test_finance_and_legal_hard_requirements_are_explainable`、金融 HTTP 事务 |
| 法律硬资格 | INV-QUALIFICATION-012 | AC-LEGAL-03 | 缺准入／执业证书不能通过律师岗；满足条件的商业律师可通过 | `test_finance_and_legal_hard_requirements_are_explainable`、法律 HTTP 事务 |
| 多简历路由 | INV-RESUME-013 | AC-RESUME-04 | 金融岗位选金融简历，法律岗位选法律简历；默认简历不能错误覆盖 | `test_job_specific_resume_routing_and_docx_are_fact_bounded`、HTTP 双简历反例 |
| 可下载文档 | INV-DOCUMENT-014 | AC-DOCX-05 | DOCX 可打开且内容来自选中简历，原始简历保持不变 | DOCX 解包测试、HTTP 下载测试 |
| 动态聚合 | INV-REFRESH-006 | AC-DISCOVERY-06 | 上传后自动出岗位，重复刷新去重，下一轮为六小时后 | 发现测试、重启读回、目标调度证据 |
| 全中文 | INV-CHINESE-011 | AC-CHINESE-08 | 主流程按钮、错误、标签和文档默认中文 | `test_major_candidate_surfaces_are_chinese`、UI 合同、浏览器走查 |
| 多租户 | INV-TENANT-003 | AC-TENANT-10 | A 账户无法读取 B 的简历、推荐、申请包和导出 | 租户测试、双用户 HTTP／浏览器事务 |
| 用户成果 | INV-REAL-001 | AC-CONTROLS-09 | 完整事务产生正确推荐、正确简历和可下载申请文档 | `e2e_http_v04.py`、目标 Playwright |
| 稳定读回 | INV-RECOVERY-008 | AC-PERSIST-12 | 刷新、重登、服务重启后状态不丢失 | HTTP 重启读回、生产重启与备份恢复 |
