"""公开数据面入口：``uvicorn apps.api.app.public_main:app``（容器默认入口）。"""

from __future__ import annotations

from .public.app import create_public_app

app = create_public_app()
