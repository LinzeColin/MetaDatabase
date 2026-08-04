"""那两条没敢跑的命令，它们的承诺仍然要守（v0.0.0.7 / T18）。

手册第一屏 7 条命令逐条真跑过，只有两条明确没跑：

  · `stop.sh` —— 它是 `docker compose down`，会把生产停掉
  · `load_extension_instructions.sh` —— 要在 Owner 的 Mac 上开访达窗口

跑不了不等于放着不管：**这两条各自有一个可以静态验证的承诺**，
而那个承诺一旦被人改坏，后果比命令本身跑不跑得起来严重得多。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_stop_never_removes_the_volumes_it_promises_to_keep() -> None:
    """`stop.sh` 打印的是「数据卷和长期事实未删除」。

    `docker compose down` 不带 `-v` 时确实不删卷——**那一句因此是真的**。
    但有人哪天顺手加个 `-v`（"清理干净点"），这句话就变成谎，
    而且是**在用户已经照着做完之后**才发现的那种谎。
    """
    stop = (ROOT / "scripts/stop.sh").read_text(encoding="utf-8")
    assert "数据卷和长期事实未删除" in stop, "那句承诺没了"
    code = "\n".join(l for l in stop.splitlines() if not l.lstrip().startswith("#"))
    down = [l for l in code.splitlines() if "docker compose down" in l]
    assert down, "stop.sh 不再是 docker compose down 了，这条判据要重写"
    for line in down:
        assert " -v" not in line and "--volumes" not in line, (
            f"stop.sh 会删卷，而它同时还在说「数据卷和长期事实未删除」：{line.strip()}"
        )


def test_the_two_ways_to_install_the_extension_are_the_same_thing() -> None:
    """装法有两条路，而只有一条被真浏览器验过。

    · 安装页让 Owner 解压**下载到的 ZIP**，放进「文稿」
    · `load_extension_instructions.sh` 让人加载**源码目录** apps/browser-extension

    两者一旦分叉，就会出现「验过的那个不是他装的那个」。
    2026-08-05 实测两边逐字节相同（各 23 个文件）——把它钉住。
    """
    # **每次都重打，不是「文件不在才打」。**
    #
    # 原来只在包不存在时才打，于是改完扩展源码、还没重打包时，这条判据比的是
    # **一个旧包**，报出来的差异看着像「两条装法分叉了」，其实只是包过期。
    # 2026-08-05 改 background.js 时就这么红过一次。
    # 重打是确定性的，也不慢；比的应当是「打包这一步会不会漏文件」。
    package = ROOT / "dist/social-archive-extension.zip"
    subprocess.run([sys.executable, str(ROOT / "scripts/build_extension_package.py")],
                   cwd=ROOT, check=True, capture_output=True)
    import tempfile, zipfile

    source = ROOT / "apps/browser-extension"
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(package) as archive:
            archive.extractall(tmp)
        unpacked = Path(tmp)
        packed = {p.relative_to(unpacked): p.read_bytes() for p in unpacked.rglob("*") if p.is_file()}
        original = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert set(packed) == set(original), (
        f"两条装法给的文件不一样：只在包里 {sorted(set(packed) - set(original))}；"
        f"只在源码目录 {sorted(set(original) - set(packed))}"
    )
    differing = sorted(str(name) for name in packed if packed[name] != original[name])
    assert not differing, f"同名文件内容不同：{differing}"


def test_the_extension_instructions_self_check_before_telling_you_to_load() -> None:
    """那个脚本没被跑过，但它的第一步是预检——预检本身在发布门里，是绿的。

    钉住「先自检、不过就别装」这个顺序：装一个 Chrome 会直接拒绝的扩展，
    对一个说「我没有技术基础」的人来说是最难自己走出来的坑。
    """
    raw = (ROOT / "scripts/load_extension_instructions.sh").read_text(encoding="utf-8")
    # **先把注释剥掉再比位置。** 第一版直接在原文里找 chrome://extensions，
    # 命中的是第 4 行注释里那一处（脚本开头在解释「为什么这一步只能人来做」），
    # 于是判据说「自检排在指引之后」——**而脚本本身完全是对的**。
    # 锚在注释上，本会话已经栽过不止一次。
    script = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    assert "preflight_extension.py" in script, "装载指引不先自检"
    assert "chrome://extensions" in script
    assert script.index("preflight_extension.py") < script.index("chrome://extensions"), \
        "自检排在指引之后，等于没检"
    assert "自检没过——先别装" in script, "自检失败时没有拦住"


def test_no_guard_anchors_on_a_string_that_appears_more_than_once() -> None:
    """`split(anchor, 1)` 会**静默取第一处**——而第一处常常不是你要的那处。

    2026-08-05 用这条规则当尺子量了一遍现有判据的锚点，量出一个**活的假绿**：
    `test_promised_actions_have_buttons` 里锚在 `revokePlatform` 上，
    而它在 options.js 里出现三次（前两次都在第 165 行那句事件绑定里），
    函数定义在第 205 行——600 字的窗口根本够不到。实测：往真正的
    revokePlatform 里塞一句直连 DELETE，那条判据**照样通过**。

    这里把那几个仍在用的锚点钉住：剥掉注释之后必须唯一。
    """
    ext = ROOT / "apps/browser-extension"
    checked = {
        ext / "background.js": [
            "netCaptureBuffer.length > NET_CAPTURE_LIMIT",
            "SA_PARSE_NET_CAPTURES",
            '"SA_DISCONNECT_ACCOUNT"',
            '"SA_REVOKE_PLATFORM_SESSION"',
        ],
        ext / "popup.js": ["/v1/extension/diagnostics"],
        ext / "options.js": ["const syncable"],
    }
    ambiguous = []
    for path, anchors in checked.items():
        code = "\n".join(
            l for l in path.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith(("//", "*", "/*"))
        )
        for anchor in anchors:
            count = code.count(anchor)
            if count != 1:
                ambiguous.append(f"{path.name}: {anchor!r} 出现 {count} 次")
    assert not ambiguous, (
        "这些锚点不唯一，靠它们切窗口的判据可能一直在验错地方：" + "；".join(ambiguous)
    )
