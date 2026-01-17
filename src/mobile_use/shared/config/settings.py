"""Application settings using Pydantic."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM provider settings."""
    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: str = "openai"
    model: str = "gpt-4-vision-preview"
    api_key: SecretStr | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = 4096
    timeout: int = 30


class DeviceSettings(BaseSettings):
    """Device control settings."""
    model_config = SettingsConfigDict(env_prefix="DEVICE_")

    platform: str = "android"
    adb_host: str = "localhost"
    adb_port: int = 5037
    default_timeout: int = 30
    screenshot_format: str = "png"
    screenshot_quality: int = 90


class AgentSettings(BaseSettings):
    """Agent system settings."""
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    max_iterations: int = 50
    step_timeout_ms: int = 30000
    confidence_threshold: float = 0.7
    enable_vision: bool = True
    capture_screenshots: bool = True


class LoggingSettings(BaseSettings):
    """Logging settings."""
    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_enabled: bool = True
    file_path: str = "./logs/mobile_use.log"
    console_enabled: bool = True
    console_colored: bool = True


class DatabaseSettings(BaseSettings):
    """Database settings."""
    model_config = SettingsConfigDict(env_prefix="DB_")

    type: str = "sqlite"
    path: str = "./data/mobile_use.db"
    host: str | None = None
    port: int | None = None
    name: str | None = None
    username: str | None = None
    password: SecretStr | None = None


class WebSettings(BaseSettings):
    """Web interface settings."""
    model_config = SettingsConfigDict(env_prefix="WEB_")

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    cors_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )

    # Application info
    app_name: str = "Mobile-Use"
    app_version: str = "2.0.0"
    debug: bool = False

    # Paths
    config_path: Path = Path("./config")
    data_path: Path = Path("./data")
    logs_path: Path = Path("./logs")
    screenshots_path: Path = Path("./screenshots")

    # Sub-settings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    device: DeviceSettings = Field(default_factory=DeviceSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    web: WebSettings = Field(default_factory=WebSettings)

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        for path in [self.data_path, self.logs_path, self.screenshots_path]:
            path.mkdir(parents=True, exist_ok=True)

    def get_llm_config(self) -> dict[str, Any]:
        """Get LLM configuration as dictionary."""
        return {
            "provider": self.llm.provider,
            "model": self.llm.model,
            "api_key": self.llm.api_key.get_secret_value() if self.llm.api_key else None,
            "base_url": self.llm.base_url,
            "temperature": self.llm.temperature,
            "max_tokens": self.llm.max_tokens,
            "timeout": self.llm.timeout
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
