"""
Gateway configuration — all settings loaded from environment / .env file.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Gateway ──────────────────────────────────────────
    gateway_env: Literal["development", "staging", "production"] = "development"
    gateway_host: str = "0.0.0.0"
    gateway_port: int = Field(default=8000, ge=1, le=65535)
    gateway_workers: int = Field(default=1, ge=1)
    gateway_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Ollama ───────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: float = Field(default=120.0, ge=1.0)
    ollama_max_retries: int = Field(default=3, ge=0)
    # Keep models hot in GPU memory — avoids cold-start switching latency
    ollama_keep_alive: str = "1h"

    # ── Model Routing ────────────────────────────────────
    routing_fast_tier_token_threshold: int = Field(default=300, ge=1)
    routing_fast_tier_complexity_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    routing_quality_complexity_threshold: float = Field(default=0.75, ge=0.0, le=1.0)

    # Model assignments per tier
    routing_fast_model:    str = "mistral:latest"
    routing_quality_model: str = "llama3.2:latest"
    routing_code_model:    str = "qwen2.5-coder:7b"
    routing_vision_model:  str = "llava:7b"

    routing_sla_timeout_ms: int = Field(default=30000, ge=1000)

    # ── Redis ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Observability ────────────────────────────────────
    otel_service_name: str = "inference-gateway"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    prometheus_port: int = Field(default=9090, ge=1, le=65535)

    @field_validator("ollama_base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.gateway_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings()