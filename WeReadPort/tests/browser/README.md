# 目标环境浏览器即时验收

该测试使用真实本地上传 Worker 和真实导出核心，不使用微信读书密钥，不依赖外网，不等待真实时间。

```bash
# 终端一
npm run build:portable
npm run dev:portable

# 终端二：使用目标仓已安装的 Playwright；不存在时按官方方式安装
WEREAD_PORT_URL=http://127.0.0.1:4187 \
WEREAD_PORT_EVIDENCE=/tmp/weread-port-browser-evidence \
python3 tests/browser/whitebox_test.py
```

覆盖：本地 Markdown/TXT 上传、浏览器隔离解析、会话 Fake Clock、显式 ZIP 下载、显式 ChatGPT Markdown 下载、中文提问词复制、固定 `https://chatgpt.com/` 跳转、URL 无笔记数据、无自动下载、无浏览器长期存储、320px Reflow 和 Reduced Motion。

当前构建环境的系统 Chromium 受企业 `URLBlocklist=["*"]` 策略限制，因此本脚本作为目标环境部署前的即时硬验收，不把环境阻塞写成 PASS，也不绕过系统策略。
