"""备份写得进去，按文档的恢复路却取不出来（v0.0.0.7 / T16 / INV-REVERSIBLE）。

2026-08-04 实测，同一个制品做三仓取回演练：

    r2      success
    oci     success
    github  **FAIL — GITHUB_RELEASE_READ_FAILED**

而库里三份副本全是 `status=verified`。**「登记成 verified」和「取得回来」
是两件事。**

根因：两个 GitHub 令牌，能看见的东西不一样。

    github_token          → GraphQL: Could not resolve to a Repository
                            with the name 'LinzeColin/Private-Database'
    github_markdown_token → {"nameWithOwner":"LinzeColin/Private-Database"}

复制单元（写备份那条路）加载的一直是 github_markdown_token；
只有恢复脚本加载了另一个看不见私有仓的令牌。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESTORE = ROOT / "scripts/restore_object_systemd.sh"
REPLICATION = ROOT / "deploy/systemd/social-archive-replication.service"

_SOURCE = re.compile(r"LoadCredential=github_token:(\S+)")


def _source_file(text: str) -> str:
    matches = _SOURCE.findall(
        "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    )
    assert matches, "找不到 github_token 的 LoadCredential"
    assert len(set(matches)) == 1, f"同一个文件里加载了不止一个来源：{set(matches)}"
    return matches[0]


def test_restore_and_backup_load_the_same_github_credential() -> None:
    """写进去用哪把钥匙，取出来就得用哪把。"""
    restore_source = _source_file(RESTORE.read_text(encoding="utf-8"))
    backup_source = _source_file(REPLICATION.read_text(encoding="utf-8"))
    assert restore_source == backup_source, (
        f"备份用 {backup_source}，恢复用 {restore_source}——"
        "备份写得进去，恢复取不出来"
    )


def test_it_is_the_one_that_can_see_the_private_vault() -> None:
    """钉住具体是哪一个。两边一致但两边都错，上一条判据看不出来。"""
    assert _source_file(RESTORE.read_text(encoding="utf-8")).endswith("github_markdown_token"), (
        "恢复路加载的不是能看见 Private-Database 的那个令牌"
    )


def test_it_refuses_a_target_that_private_tmp_would_swallow() -> None:
    """`--target /tmp/...` 会报 PASS 而文件根本不在（v0.0.0.7 / T16）。

    包装脚本用 `systemd-run --property=PrivateTmp=yes` 起单元，单元看到的
    /tmp 与 /var/tmp 是私有 tmpfs，跑完就没了。

    2026-08-04 实测：`--target /tmp/xxx/restored.bin` 返回
    `{"status":"PASS", …, "target_written": true}`，宿主机上那个目录是空的。
    **真出事的时候，你会以为文件已经恢复出来了，手里却什么都没有。**
    """
    text = RESTORE.read_text(encoding="utf-8")
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "PrivateTmp=yes" in code, "判据失去依附：这条属性没了就不需要这道拦截了"
    assert "/tmp/*|/var/tmp/*" in code, "没有拦住会被私有 tmpfs 吞掉的目标"
    # 拦截必须在真正起单元之前
    guard_at = code.index("/tmp/*|/var/tmp/*")
    run_at = code.index("systemd-run")
    assert guard_at < run_at, "拦在起单元之后，文件已经写进私有 tmpfs 了"
