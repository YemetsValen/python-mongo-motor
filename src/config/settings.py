"""
Application settings using pydantic-settings.

Loads configuration from environment variables with validation.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, MongoDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MongoSettings(BaseSettings):
    """MongoDB connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="MONGO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="MongoDB host")
    port: int = Field(default=27017, ge=1, le=65535, description="MongoDB port")
    root_user: str = Field(default="admin", description="MongoDB root username")
    root_password: SecretStr = Field(
        default=SecretStr("secret"), description="MongoDB root password"
    )
    db_name: str = Field(default="predictions_db", description="Database name")
    auth_source: str = Field(default="admin", description="Authentication database")

    # Connection pool settings
    min_pool_size: int = Field(default=5, ge=1, description="Minimum connection pool size")
    max_pool_size: int = Field(default=50, ge=1, description="Maximum connection pool size")
    max_idle_time_ms: int = Field(default=60000, ge=0, description="Max idle time in milliseconds")

    # Timeouts
    connect_timeout_ms: int = Field(default=5000, ge=1000, description="Connection timeout in ms")
    server_selection_timeout_ms: int = Field(
        default=5000, ge=1000, description="Server selection timeout in ms"
    )

    @computed_field  # type: ignore[misc]
    @property
    def uri(self) -> str:
        """Build MongoDB connection URI."""
        password = self.root_password.get_secret_value()
        return (
            f"mongodb://{self.root_user}:{password}@{self.host}:{self.port}"
            f"/{self.db_name}?authSource={self.auth_source}"
        )


class AppSettings(BaseSettings):
    """Application-level settings."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = Field(default="Match Predictions System", description="Application name")
    version: str = Field(default="0.1.0", description="Application version")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Environment name",
    )
    debug: bool = Field(default=False, description="Debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Pagination defaults
    default_page_size: int = Field(default=20, ge=1, le=100, description="Default page size")
    max_page_size: int = Field(default=100, ge=1, le=1000, description="Maximum page size")


class Settings(BaseSettings):
    """Main settings container."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongo: MongoSettings = Field(default_factory=MongoSettings)
    app: AppSettings = Field(default_factory=AppSettings)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()


# Convenience alias
settings = get_settings()
