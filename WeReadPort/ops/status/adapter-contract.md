# LinzeStatus 状态适配契约

`weread-port-ops monitor` 只写入一个脱敏 JSON 对象。对象中的 `project` 字段沿用既有 LinzeStatus 收集器已消费的字段：`name`、`url`、`parts`、`host`、`db`、`store`、`deploy`、`backup`、`agent`、`notify`。

安装器只增加一个有界文件加载器，并扩展既有 `PROJECTS` 循环；不会加入凭证、执行外部代码，也不会让“微信读书笔记迁移”成为状态收集器的关键依赖。适配文件缺失或无效时应忽略该项目，其他状态采集继续运行。
