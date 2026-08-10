#!/bin/bash
# 双击这个文件，就会把服务器上的收藏同步进你的 Obsidian 库。
#
# 为什么有它：Owner 说过「我没有技术基础」，而在这之前我给他的是一条
# 要在终端里敲的命令。这个文件双击就跑，跑完停住给他看结果。

SCRIPT="$HOME/Documents/Codex/GithubProject/_scratch/metadatabase-social-archive-v0007/social-archive/scripts/pull_markdown_to_obsidian.sh"

clear
echo "把收藏同步到 Obsidian"
echo "────────────────────────────────"
echo

if [[ ! -f "$SCRIPT" ]]; then
  echo "找不到同步脚本："
  echo "  $SCRIPT"
  echo
  echo "多半是项目文件夹被移动或删掉了。把这个情况告诉我就行。"
  echo
  read -n 1 -s -r -p "按任意键关闭"
  exit 1
fi

bash "$SCRIPT"
STATUS=$?

echo
if [[ $STATUS -eq 0 ]]; then
  echo "────────────────────────────────"
  echo "好了。打开 Obsidian，左边那个「Social Archive」文件夹里就是。"
else
  echo "────────────────────────────────"
  echo "没跑成（退出码 $STATUS）。上面那段话就是原因，截给我看即可。"
fi
echo
read -n 1 -s -r -p "按任意键关闭这个窗口"
echo
