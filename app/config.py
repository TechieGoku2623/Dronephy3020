"""Environment-driven runtime configuration for SaaS deployments."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None or not value.strip():
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_api_keys(value: str | None) -> dict[str, str]:
    """
    Parse keys from either:
    - "name1:key1,name2:key2"
    - "key1,key2" (auto names key_1, key_2)
    """
    if value is None or not value.strip():
        return {}

    key_map: dict[str, str] = {}
    raw_items = [item.strip() for item in value.split(",") if item.strip()]
    for index, raw_item in enumerate(raw_items, start=1):
        if ":" in raw_item:
            name, token = raw_item.split(":", maxsplit=1)
            name, token = name.strip(), token.strip()
        else:
            name, token = f"key_{index}", raw_item

        if name and token:
            key_map[name] = token
    return key_map


@dataclass(frozen=True)
class Settings:
    """Runtime settings for API security, limits, and deployment behavior."""

    app_name: str
    app_version: str
    environment: str
    cors_origins: list[str]
    weather_api_base: str
    require_api_key: bool
    api_keys: dict[str, str]
    default_tenant_id: str
    enforce_tenant_header: bool
    enable_rate_limit: bool
    rate_limit_per_minute: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Create immutable settings snapshot from environment variables."""
        app_name = os.getenv("GRIDOS_APP_NAME", "GridOS-Logic v2.0")
        app_version = os.getenv("GRIDOS_APP_VERSION", "2.1.0")
        environment = os.getenv("GRIDOS_ENV", "development").strip().lower()
        cors_origins = _parse_csv(
            os.getenv("GRIDOS_CORS_ORIGINS"),
            default=["http://localhost:3000", "http://localhost:5173"],
        )
        weather_api_base = os.getenv("WEATHER_API_BASE", "").strip()
        require_api_key = _parse_bool(os.getenv("GRIDOS_REQUIRE_API_KEY"), default=False)
        api_keys = _parse_api_keys(os.getenv("GRIDOS_API_KEYS"))
        default_tenant_id = os.getenv("GRIDOS_DEFAULT_TENANT_ID", "public").strip().lower()
        enforce_tenant_header = _parse_bool(os.getenv("GRIDOS_ENFORCE_TENANT_HEADER"), default=False)
        enable_rate_limit = _parse_bool(os.getenv("GRIDOS_ENABLE_RATE_LIMIT"), default=True)
        rate_limit_per_minute = int(os.getenv("GRIDOS_RATE_LIMIT_PER_MINUTE", "180"))
        log_level = os.getenv("GRIDOS_LOG_LEVEL", "INFO").upper()

        return cls(
            app_name=app_name,
            app_version=app_version,
            environment=environment,
            cors_origins=cors_origins,
            weather_api_base=weather_api_base,
            require_api_key=require_api_key,
            api_keys=api_keys,
            default_tenant_id=default_tenant_id,
            enforce_tenant_header=enforce_tenant_header,
            enable_rate_limit=enable_rate_limit,
            rate_limit_per_minute=rate_limit_per_minute,
            log_level=log_level,
        )
