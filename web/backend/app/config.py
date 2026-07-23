from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    dify_base_url: str = "https://api.dify.ai/v1"
    dify_api_key: str = ""
    dify_concurrency: int = 3
    dify_timeout_seconds: float = 120
    task_ttl_seconds: int = 7200
    app_access_code: str = ""
    session_secret: str = ""
    session_ttl_seconds: int = 28800
    session_cookie_secure: bool = False
    per_ip_daily_resume_limit: int = 10
    global_daily_resume_limit: int = 50
    quota_timezone: str = "Asia/Shanghai"
    quota_db_path: str = ""
    max_request_bytes: int = 4 * 1024 * 1024
    trust_proxy_headers: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
