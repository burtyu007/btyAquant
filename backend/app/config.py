from __future__ import annotations

import os


class Settings:
    app_name = "Quant Platform API"
    api_prefix = "/api"
    mysql_host = os.getenv("MYSQL_HOST", "host.docker.internal")
    mysql_port = int(os.getenv("MYSQL_PORT", "3380"))
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "Burtyu1989")
    mysql_db = os.getenv("MYSQL_DB") or os.getenv("MYSQL_DATABASE", "quant")
    redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))
    redis_password = os.getenv("REDIS_PASSWORD", "")
    redis_key_prefix = os.getenv("REDIS_KEY_PREFIX", "quant-platform")
    secret_key = os.getenv("SECRET_KEY", "quant-platform-dev-secret")
    access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    cors_origins = [
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
        if item.strip()
    ]

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


settings = Settings()
