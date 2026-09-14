#!/usr/bin/env python3
"""Generate a production .env file with strong API keys."""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path


def build_env(
    domain: str,
    tenant_id: str,
    weather_api_base: str,
    rate_limit_per_minute: int,
    workers: int,
    timeout_seconds: int,
) -> str:
    ops_token = secrets.token_urlsafe(48)
    monitor_token = secrets.token_urlsafe(48)
    cors_origin = f"https://{domain}"

    lines = [
        "GRIDOS_ENV=production",
        "GRIDOS_LOG_LEVEL=INFO",
        "GRIDOS_APP_VERSION=2.1.0",
        "",
        f"GRIDOS_CORS_ORIGINS={cors_origin}",
        "",
        "GRIDOS_REQUIRE_API_KEY=true",
        f"GRIDOS_API_KEYS=ops:{ops_token},monitor:{monitor_token}",
        f"GRIDOS_DEFAULT_TENANT_ID={tenant_id}",
        "GRIDOS_ENFORCE_TENANT_HEADER=true",
        "",
        "GRIDOS_ENABLE_RATE_LIMIT=true",
        f"GRIDOS_RATE_LIMIT_PER_MINUTE={rate_limit_per_minute}",
        "",
        f"GRIDOS_API_WORKERS={workers}",
        f"GRIDOS_API_TIMEOUT_SECONDS={timeout_seconds}",
        "",
        f"WEATHER_API_BASE={weather_api_base}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GridOS production env file.")
    parser.add_argument("--domain", required=True, help="Frontend domain without protocol, e.g. app.example.com")
    parser.add_argument("--tenant-id", default="public", help="Default tenant id.")
    parser.add_argument("--weather-api-base", default="", help="Optional weather API endpoint.")
    parser.add_argument("--rate-limit", type=int, default=240, help="Requests per minute.")
    parser.add_argument("--workers", type=int, default=2, help="API worker count.")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="API timeout seconds.")
    parser.add_argument("--output", default=".env", help="Output file path.")
    args = parser.parse_args()

    env_content = build_env(
        domain=args.domain.strip(),
        tenant_id=args.tenant_id.strip().lower(),
        weather_api_base=args.weather_api_base.strip(),
        rate_limit_per_minute=args.rate_limit,
        workers=args.workers,
        timeout_seconds=args.timeout_seconds,
    )
    output_path = Path(args.output)
    output_path.write_text(env_content, encoding="utf-8")
    print(f"Wrote production environment file: {output_path}")


if __name__ == "__main__":
    main()
