from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "FACTAPI_", "env_file": ".env", "extra": "ignore"}

    db_path: str = "data/factapi.db"
    api_key: str = ""
    admin_key: str = ""
    default_limit: int = 100
    max_limit: int = 1000
    env: str = "development"
    cors_origins: str = "*"
    log_level: str = "info"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
