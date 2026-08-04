"""突变探针：把判据断言的那个字面量从源码里删掉，看判据会不会红。

断言绿着不代表它在守什么。唯一的证明是：**把它守的东西弄坏，它必须变红。**

**归属要靠得住**，否则「没守住」全是探针自己认错了文件。第一版把
`umask 0007` 归给 prepare_systemd_host.sh（那里只在注释里提过一次），
于是删错了文件、判据当然不红，被报成「这条判据没在守什么」。

## 它**没有**被挂进发布门，这是有意的

2026-08-05 跑了约 70 次突变，报出 7 处「没守住」——**逐个查完，7 处全是
这个探针自己认错了文件**：
  · "127.0.0.1" 断言打的是演练脚本，它去删了 background.js
  · "/v1/credentials" 断言打的是 api.py，它去删了 background.js
  · "Path(identity).is_file()" 断言打的是 restore.py，它去删了 restore_object.py
  · "credential_age_recipient" 断言打的是 Settings 的字段，它去删了 api.py
  · "umask 0007" / "SACookieExport" / "HttpOnly" 同理

也就是说：**能正确归属的那些，一个不漏全是承重的**——这是个好消息。
而这个探针的归属靠的是「判据文件里出现过哪些源码路径字面量」，
太弱，做不了门。**一个 100% 误报率的门，用不了几次就会被整段跳过**，
那时它连真的问题也挡不住——本仓已经在 doctor.sh 的 16 个假 FAIL 上
学过这一课。

所以它留在这里当**手动工具**：改完一批判据之后跑一次，逐个人工过一遍
报出来的那几条。要把它变成门，先得把归属做成真的（跟着变量走，
而不是猜文件）。

用法：`python3 scripts/probe_guards_are_load_bearing.py [突变次数上限]`
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(".")
ASSERT = re.compile(r'assert\s+"([^"\\]{8,60})"\s+in\s+\w+')
PATHREF = re.compile(r'"((?:apps|src|scripts)/[^"]+\.(?:js|py|sh))"')


def code_only(path: pathlib.Path) -> str:
    marks = ("//", "*", "/*") if path.suffix in {".js", ".mjs"} else ("#",)
    return "\n".join(
        line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not line.lstrip().startswith(marks)
    )


def main() -> int:
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    results = {"load_bearing": 0, "not_load_bearing": [], "skipped": 0}
    for test in sorted(pathlib.Path("tests/focused").glob("test_*.py")):
        if budget <= 0:
            break
        body = test.read_text(encoding="utf-8")
        if "inspect.getsource" in body:      # 断言打的是标准库，不是仓里的文件
            continue
        targets = [ROOT / m for m in dict.fromkeys(PATHREF.findall(body)) if (ROOT / m).is_file()]
        if not targets:
            continue
        for literal in dict.fromkeys(ASSERT.findall(body)):
            if budget <= 0:
                break
            owners = [t for t in targets if code_only(t).count(literal) == 1]
            if len(owners) != 1:
                results["skipped"] += 1
                continue
            source = owners[0]
            original = source.read_text(encoding="utf-8")
            mutated = "\n".join(l for l in original.splitlines() if literal not in l)
            if mutated == original:
                results["skipped"] += 1
                continue
            budget -= 1
            source.write_text(mutated, encoding="utf-8")
            try:
                run = subprocess.run([sys.executable, "-m", "pytest", str(test), "-q", "-x"],
                                     capture_output=True, text=True, timeout=180)
                red = run.returncode != 0
            finally:
                source.write_text(original, encoding="utf-8")
            if red:
                results["load_bearing"] += 1
            else:
                results["not_load_bearing"].append(
                    {"test": test.name, "source": source.name, "literal": literal})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
