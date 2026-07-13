"""集中配置模块 —— 全仓唯一读取环境变量处。

架构规则（scripts/checks/core_duplication.py）要求：所有 os.getenv/os.environ
只能出现在 config.py / settings.py。其他模块一律从这里的 `settings` 读取。

用 pydantic-settings 从环境变量与 .env 加载，字段即文档。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。字段名对应环境变量名（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 访问控制（共享口令） ----
    shared_passphrase: str = "changeme"  # 团队共享登录口令
    session_secret: str = "dev-insecure-secret-change-me"  # cookie 签名密钥
    session_cookie_name: str = "douyin_session"
    session_max_age_seconds: int = 7 * 24 * 3600  # 会话有效期

    # ---- LLM（OpenAI-compatible） ----
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    mock_llm: bool = True  # 无 Key/离线时走占位输出，保证端到端可验收

    # ---- 转写（faster-whisper） ----
    whisper_model_size: str = "small"  # 默认 small，平衡中文质量/速度/资源
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    mock_transcribe: bool = True  # 无 GPU/无模型时走占位转写稿

    # ---- 数据目录 ----
    data_dir: Path = Path("data")

    # ---- 抖音下载（本阶段留桩，Cookie 从环境注入，不在 UI 填） ----
    douyin_cookie: str = ""

    # ---- 上传 ----
    upload_max_mb: int = 200

    # ---- 文件保留 ----
    media_retention_days: int = 7

    # ---- 服务器 ----
    host: str = "0.0.0.0"
    port: int = 8000
    production_mode: bool = False  # True 时禁用 uvicorn 热重载

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例配置。其他模块用 `from app.config import get_settings`。"""
    return Settings()


settings = get_settings()
