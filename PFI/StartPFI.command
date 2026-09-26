#!/bin/sh
# macOS 双击快捷方式：只调用跨平台入口 `python -m pfi_os app`。
# 需要先 `pip install -e "PFI[app]"`，并在 ~/.pfi/env 或环境里设置 PFI_DATA_DIR。
cd "$(dirname "$0")" || exit 1
if [ -f "$HOME/.pfi/env" ]; then set -a; . "$HOME/.pfi/env"; set +a; fi
exec "${PFI_PYTHON:-python3}" -m pfi_os app
