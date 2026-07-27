# PG-5 Final Publication Receipt

本节点只在 CB-540 Subject、deployment digest、provider receipts、rollback receipt 和外部验收候选
均已密封后关闭。开发候选为 `MVP_DEGRADED`；`FORMAL_FINAL_ACCEPTANCE=BLOCKED` 仅表示两个独立
外部 contexts 未在开发 DAG 中执行。

publication 只使用现有 branch：不创建仓库、tag、PR、平行证据库或 Private-Database clone；closure
commit 后执行一次该 branch 的 push。该提交前没有中间 push、PR 或 tag。工作树在最终封签后必须 clean，
并保留 `fd3cd1e19d70caa148c3785288aaabfb909fed85` 为 deployed current、
`25670bf32c6d27e3668fcf59bc9ab754035e161d` 为 rollback previous。
