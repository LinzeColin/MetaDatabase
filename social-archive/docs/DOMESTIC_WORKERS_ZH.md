# 东方平台 Worker：小白操作

1. 首次安装后运行 `bash scripts/start_workers.sh stable`。它只启动小红书与快手两个已能非交互进入 API 模式的隔离 Worker。
2. 打开 `http://127.0.0.1:18765`，粘贴本人可访问链接并选择对应平台。下载文件先进入 `runtime/vendor-output/`，随后自动纳入 Social Archive 内容寻址仓。
3. 抖音默认先尝试 DouK；未通过健康门时自动使用容器内 `gallery-dl`、`yt-dlp`，再不行仍可用 Chrome 扩展保存当前页面。不会让整个系统失效。
4. 只有需要试验 DouK Web API 时才运行 `bash scripts/start_workers.sh douk-experimental`。该上游版本仍有交互式启动限制，因此不作为正式可用性的唯一依赖。
5. 停止 Worker：`bash scripts/stop_workers.sh`。核心资料库继续运行。

所有 Worker 都是独立进程/容器。Social Archive 不复制 GPL 源码、不接收密码、不绕过验证码、设备风控或访问控制。

这些 Worker 在架构上统一称为 Sidecar：它们可单独启动、停止、升级和熔断，不能把第三方代码或登录态带入 Core。
