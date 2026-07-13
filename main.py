"""运行入口：uv run python main.py 启动 FastAPI 服务。

配置（host/port/生产模式）集中在 app.config 读取，见 .env / 环境变量。
"""

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=not settings.production_mode,
    )


if __name__ == "__main__":
    main()
