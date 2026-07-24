# age 加密、Secret 与恢复钥匙交付

## 1. 数据加密

全部敏感对象使用 age X25519 Recipient 流式加密。日常 Ingest 只需要公开 Recipient；只有受保护 Recovery/Reprocess 环境需要 Identity。

## 2. 持久化前原则

```text
Gmail/API plaintext
→ process memory or tmpfs
→ age stream
→ ciphertext
→ Git/LFS/Release persistence
```

不得先写普通 Runner Disk 再加密；不得上传明文 Artifact/Cache。

## 3. 部署时生成

任务包不包含真实密钥。开发线程在生产部署 Gate 中：

1. 在受保护 GitHub-hosted 临时环境生成 `age-keygen` Identity；
2. 提取公开 Recipient 并提交到公开配置；
3. 将私有 Identity 写入受保护 GitHub Environment Secret；
4. 通过开发线程提供一次性下载文件 `MooMooAU-Recovery-Key.agekey`；
5. 用户下载后，Runner 明文私钥销毁；
6. 用下载文件完成一次随机样本恢复验收；
7. 未完成步骤 4–6 不允许启用 M3。

私钥永不打印、永不进入聊天正文、Git、PR、Issue、日志或任务包 ZIP。

## 4. Moomoo PDF Password

另一个 Secret，只用于打开 Moomoo 内部加密 PDF。系统不保存手机号/证件号，也不暴力破解。Secret 不存在时记录 `WAITING_FOR_PDF_PASSWORD`；Raw、附件、远端恢复和 M3 继续。

## 5. Key Epoch

Raw 不因密钥轮换而反复重加密。新 Recipient 从某个 Epoch 起应用于新对象；历史对象保留对应旧 Identity 恢复能力。每个对象的 Private Manifest 记录 Epoch，不在公开面暴露。

## 6. 轮换与事件

- Operational Identity 暴露：立即停机，对新数据生成新 Epoch；评估历史密文风险。
- Recovery 文件丢失但 Secret 可用：在受保护环境生成新的恢复交付方案，不打印原 Secret。
- Secret 与 Recovery 均丢失：历史密文可能不可恢复，触发 KILL-005。
