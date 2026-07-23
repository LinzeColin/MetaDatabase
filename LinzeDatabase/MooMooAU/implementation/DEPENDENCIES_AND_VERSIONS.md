# 普通依赖穷尽与版本策略

## 建议技术栈

- Python 3.12+；
- `google-api-python-client` / `google-auth`：Gmail API；
- `httpx`：受 endpoint guard 控制的 REST；
- `pydantic` 或 dataclass：内部模型；
- `jsonschema`：交换契约；
- `pandera` + `pyarrow`：Parquet/DataFrame 验证；
- `pikepdf`：受限 PDF 检查/解密；
- `openpyxl`：只读 XLSX 解析，禁用外部链接/宏执行；
- `python-magic` 或等效纯检测库：Magic Bytes；
- `cryptography`/系统 age CLI：以官方 age 二进制为主；
- `exchange_calendars` 或受固定版本控制的 NYSE 日历；
- `matplotlib`：确定性 Timeline PNG；
- `pytest`、Hypothesis、Atheris/等价 Fuzz、Ruff、mypy/pyright；
- `pip-audit`/OSV、CodeQL、Syft/CycloneDX：供应链。

## 选择原则

- 优先成熟、维护活跃、许可清晰、可固定版本的库；
- 不为单一功能引入常驻服务、数据库、消息队列或浏览器自动化；
- 不依赖 Moomoo 私有 API 或网页抓取；
- 不采用需要用户电脑守护进程的工具；
- 依赖版本最终由开发线程在实现时锁定，并记录选择证据、替代品和升级测试。

## 预授权可逆决策

开发线程可在不询问用户的情况下：选择同类 Python 库、目录内文件名、内部类名、测试框架配置、重试参数、批次大小和图表排版，只要不改变冻结不变量、公开 Schema 或权限边界。
