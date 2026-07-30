# 公网部署结果合同

Build Agent 只有在以下命令通过后才能回复“已完成”：

```bash
python3 Signal-Lattice/scripts/verify_public_release.py \
  --url https://signal-lattice.linzezhang.com \
  --version 0.0.0.1.40 \
  --output /var/lib/signal-lattice/artifacts/public_release.json

python3 Signal-Lattice/scripts/verify_deployment_claim.py \
  --result /var/lib/signal-lattice/artifacts/DELIVERY_RESULT.json \
  --version 0.0.0.1.40
```

最终回复必须逐项给出：

- `https://signal-lattice.linzezhang.com`
- `https://status.linzezhang.com`
- `DELIVERY_RESULT.json` 的 SHA-256
- 当前 Action
- 当前是否已有可执行建议
- 若为 `NO_ACTION`，列出实际硬门原因

公网不可访问、Status 未关闭、版本不匹配、收据缺失或收据 Hash 不一致时，必须报告 `BLOCKED`，不得以“代码完成”替代。
