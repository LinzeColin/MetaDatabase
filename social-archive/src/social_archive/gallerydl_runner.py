"""gallery-dl 子进程运行器（v0.0.0.7 / T07 + T12 共用）。

## 为什么是子进程而不是 import

任务包的 suggested_path 原话：「gallery-dl 以子进程调用，禁止 import 进运行路径
（许可证与稳定性）」。两条理由都成立：

  · **许可证**：gallery-dl 是 GPL-2.0。import 进本产品的进程会让许可证问题
    传导到整个运行路径；子进程调用是清楚的边界。
  · **稳定性**：上游一次异常不能把我们的 worker 拖死。

## `-j` 的三元组契约（已固化）

`gallery-dl -j` 输出一个数组，每个元素是 `[类型, ...]`：

    2  目录/元数据    [2, {metadata}]
    3  文件           [3, url, {metadata}]
    6  队列（子任务）  [6, url, {metadata}]
    -1 错误           [-1, {"error": ..., "message": ...}]

样本已固化在 `evidence/fixtures/gallerydl/gallerydl_dumpjson_contract.real.json`。
**上游输出与固化 fixture 不符时，按 CONFLICT_ORDER 记录后再动，不要猜着改解析器**
（T07 的 Stop Condition 原文）。

## Reddit 未授权不是网络问题

未授权时 gallery-dl 拿到的是 Reddit 的 HTML 页面而不是 API，直接
`AbortExtraction`，错误信息里是一堆 CSS。样本已固化。

**这个绝不能当成网络抖动去重试**——重试一万次也一样，它就是缺 OAuth。
把它错判成可重试的后果是：界面转圈、日志刷屏、用户等半天，
最后还是 0 条，而且没人说得出为什么。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

# 错误信息保留前 2KB（T07 suggested_path）。Reddit 那条能有 100KB 的 CSS，
# 原样存进库会把 sync_run 撑爆，而前 2KB 已经足够辨认是哪种失败。
ERROR_MESSAGE_LIMIT = 2048

# 三元组契约的类型码。写成常量而不是散在代码里的魔数，
# 是为了让"上游改了契约"这件事在一个地方就能看出来。
KIND_DIRECTORY = 2
KIND_FILE = 3
KIND_QUEUE = 6
KIND_ERROR = -1


@dataclass
class GalleryDLResult:
    """一次 gallery-dl -j 的结果。"""

    items: list[dict[str, Any]] = field(default_factory=list)
    queued_urls: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    failure_code: str | None = None
    returncode: int = 0

    @property
    def ok(self) -> bool:
        return self.failure_code is None and not self.errors


def _looks_like_markup(message: str) -> bool:
    """判断错误信息是不是网页而不是错误描述。

    Reddit 未授权时 gallery-dl 把整个 HTML/CSS 塞进 message。
    判据打在**形态**上而不是某个固定字符串上——Reddit 换个皮肤，
    CSS 内容会全变，但"这是一坨样式表"这件事不会变。
    """
    head = message[:4000]
    markers = ("--rem", "{--", "<!doctype", "<html", ":root{", "@media", "</div>", "rgba(")
    hits = sum(1 for marker in markers if marker in head.lower() or marker in head)
    return hits >= 2


# gallery-dl 的**进程退出码是位掩码，不是单值**。实测自装机源码 1.32.8：
#   job.py:172/178  self.status |= exc.code        —— 每个异常把自己的位或进去
#   __init__.py:466 retval    |= 64                —— 顶层「URL 不受支持」
# 一次跑里出两种错就会 OR 在一起（鉴权 16 + 抽取 4 = 20）。
# 所以判定**必须按位与**：写成 `rc == 16` 会把 20 漏掉，又变成一次静默的零。
EXIT_GENERIC = 1  # GalleryDLException / JSON 解析失败 / 未预期异常
EXIT_EXTRACTION = 4  # AbortExtraction, ExtractionError, HttpError, NotFoundError
EXIT_CHALLENGE = 8  # ChallengeError —— 验证码/风控挑战
EXIT_AUTH = 16  # AuthRequired, AuthenticationError, AuthorizationError
EXIT_INPUT_FORMAT = 32  # NoExtractorError, InputError, Filter/FormatError
EXIT_NO_EXTRACTOR = 64  # 顶层：这个 URL 没有对应的 extractor
EXIT_OS = 128  # OSError（磁盘或网络 I/O）


def classify_exit_code(returncode: int, *, url: str = "", stderr: str = "") -> str | None:
    """只凭退出码（必要时加 stderr）判失败类型。

    存在的理由：**gallery-dl 失败时 stdout 是空的**，错误只写到 stderr。
    实测 `gallery-dl -j --no-download not-a-url` → exit 64、stdout 0 字节。
    只看 stdout 的话，一次硬失败和「跑完了、没有新增」长得一模一样。

    位的检查顺序 = 严重性顺序：鉴权比抽取错误更需要先说，因为它决定了
    用户下一步该做什么（去授权，而不是重试）。
    """
    rc = int(returncode or 0)
    if rc == 0:
        return None
    if rc & EXIT_AUTH:
        # Reddit 缺 OAuth 与「某平台会话过期」对用户是两件事：前者去授权，后者重连。
        return "REDDIT_NOT_AUTHORIZED" if "reddit" in url.lower() else "CREDENTIAL_EXPIRED"
    if rc & EXIT_CHALLENGE:
        # 验证码/设备风控。我们**不绕**（L0 边界），只能把人引回浏览器自己过。
        return "CHALLENGE_REQUIRED"
    if rc & (EXIT_NO_EXTRACTOR | EXIT_INPUT_FORMAT):
        # 我们把一个它不认识的 URL 传了进去——这是我们的 bug，不是用户的。
        # 让用户「重试」是骗他，重试一万次也一样。
        return "URL_NOT_SUPPORTED"
    if rc & EXIT_OS:
        return "SERVER_UNREACHABLE"
    if rc & EXIT_EXTRACTION:
        if _looks_like_markup(stderr) and "reddit" in (url + stderr).lower():
            return "REDDIT_NOT_AUTHORIZED"
        if any(token in stderr for token in ("429", "Too Many Requests", "rate limit")):
            return "RATE_LIMITED"
        return "SERVER_UNREACHABLE"
    return "SERVER_UNREACHABLE"


def classify_failure(errors: list[dict[str, str]], *, url: str = "") -> str | None:
    """把 gallery-dl 的错误归到一个失败码上。

    返回 None 表示没有可辨认的失败。
    """
    if not errors:
        return None
    first = errors[0]
    error_type = str(first.get("error") or "")
    message = str(first.get("message") or "")

    if error_type == "AbortExtraction" and _looks_like_markup(message):
        # 拿到网页而不是 API。对 Reddit 来说这就是缺 OAuth。
        if "reddit" in url.lower() or "reddit" in message.lower()[:200]:
            return "REDDIT_NOT_AUTHORIZED"
        # 其他平台拿到网页，多半是会话过期被重定向到登录页。
        return "CREDENTIAL_EXPIRED"
    if error_type in {"AuthenticationError", "AuthorizationError"}:
        return "CREDENTIAL_EXPIRED"
    if error_type == "HttpError" and any(
        token in message for token in ("429", "Too Many Requests", "rate limit")
    ):
        return "RATE_LIMITED"
    if error_type in {"HttpError", "ConnectionError"}:
        return "SERVER_UNREACHABLE"
    return "SERVER_UNREACHABLE"


def parse_dump_json(payload: Any, *, url: str = "") -> GalleryDLResult:
    """解析 `gallery-dl -j` 的输出。

    容忍单个元素形态异常（跳过并记一条错误），但**不猜**：
    认不出的类型码原样记进 errors，而不是当成文件混进结果里。
    """
    result = GalleryDLResult()
    if not isinstance(payload, list):
        result.errors.append({"error": "ContractViolation", "message": "顶层不是数组"})
        result.failure_code = "SERVER_UNREACHABLE"
        return result

    for entry in payload:
        if not isinstance(entry, list) or not entry:
            result.errors.append({"error": "ContractViolation", "message": str(entry)[:200]})
            continue
        kind = entry[0]
        if kind == KIND_ERROR:
            detail = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
            result.errors.append({
                "error": str(detail.get("error") or "Unknown"),
                "message": str(detail.get("message") or "")[:ERROR_MESSAGE_LIMIT],
            })
        elif kind == KIND_FILE and len(entry) >= 3:
            metadata = entry[2] if isinstance(entry[2], dict) else {}
            result.items.append({"url": str(entry[1]), **metadata})
        elif kind == KIND_QUEUE and len(entry) >= 2:
            result.queued_urls.append(str(entry[1]))
        elif kind == KIND_DIRECTORY:
            continue  # 目录/元数据条目本身不入库
        else:
            result.errors.append({
                "error": "ContractViolation",
                "message": f"未知类型码 {kind!r}——上游契约可能变了，按 CONFLICT_ORDER 记录后再改解析器",
            })

    result.failure_code = classify_failure(result.errors, url=url)
    return result


def run(
    url: str,
    *,
    cookies_path: str | None = None,
    limit: int | None = None,
    binary: str = "gallery-dl",
    timeout: int = 300,
    runner=None,
) -> GalleryDLResult:
    """跑一次 `gallery-dl -j`。

    `runner` 只为判据存在——注入一个假的就能在没有 gallery-dl 的机器上测解析路径。
    """
    argv = [binary, "-j", "--no-download"]
    if cookies_path:
        argv += ["--cookies", cookies_path]
    if limit:
        # 小样探测：先跑 --range 1-N 看契约对不对，再全量（T07 的 probe）
        argv += ["--range", f"1-{int(limit)}"]
    argv.append(url)

    if runner is None:
        resolved = shutil.which(binary)
        if not resolved:
            out = GalleryDLResult(failure_code="SERVER_UNREACHABLE")
            out.errors.append({"error": "MissingBinary", "message": "服务器上没有 gallery-dl"})
            return out
        argv[0] = resolved

        def runner(command):  # noqa: E306
            return subprocess.run(command, capture_output=True, text=True,
                                  check=False, timeout=timeout)

    completed = runner(argv)
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        out = GalleryDLResult(returncode=completed.returncode)
        out.errors.append({
            "error": "ContractViolation",
            "message": (completed.stderr or completed.stdout or "")[:ERROR_MESSAGE_LIMIT],
        })
        out.failure_code = classify_failure(out.errors, url=url)
        return out

    result = parse_dump_json(payload, url=url)
    result.returncode = completed.returncode

    # ——— INV-NO-SILENT-ZERO 的落点，别删 ———
    # 退出码非 0，但 JSON 里一条错误都没有。这不是罕见分支，而是 gallery-dl
    # 失败时的**常态**：它把错误写 stderr，stdout 留空。
    # 实测（生产 cli-tools 容器，gallery-dl 1.32.8）：
    #     gallery-dl -j --no-download not-a-url  → exit 64, stdout 0 字节
    # 而上面 `json.loads(completed.stdout or "[]")` 会把空 stdout 变成 `[]`，
    # 于是 items=0、errors=0、classify_failure 回 None、failure_code=None，
    # 最后 describe_sync_outcome 说「已经是最新的，没有新增内容。」
    # ——一次硬失败被显示成好消息，正是 v0.0.0.6 那种静默的零。
    if completed.returncode and result.failure_code is None:
        stderr = (getattr(completed, "stderr", "") or "")[:ERROR_MESSAGE_LIMIT]
        result.errors.append({
            "error": f"ExitCode{int(completed.returncode)}",
            "message": stderr or f"gallery-dl 以退出码 {int(completed.returncode)} 结束，且没有输出任何内容",
        })
        result.failure_code = classify_exit_code(
            completed.returncode, url=url, stderr=stderr
        )
    return result
