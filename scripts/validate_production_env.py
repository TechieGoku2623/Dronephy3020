#!/usr/bin/env python3
"""Validate GridOS production .env file for secure launch posture."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        data[key.strip()] = value.strip()
    return data


def validate(env: dict[str, str]) -> list[str]:
    issues: list[str] = []
    required = [
        "GRIDOS_ENV",
        "GRIDOS_CORS_ORIGINS",
        "GRIDOS_REQUIRE_API_KEY",
        "GRIDOS_API_KEYS",
        "GRIDOS_ENFORCE_TENANT_HEADER",
        "GRIDOS_RATE_LIMIT_PER_MINUTE",
    ]
    for key in required:
        if key not in env:
            issues.append(f"Missing required key: {key}")

    if env.get("GRIDOS_ENV") != "production":
        issues.append("GRIDOS_ENV should be 'production'.")

    if "*" in env.get("GRIDOS_CORS_ORIGINS", ""):
        issues.append("Wildcard CORS origin is not allowed in production.")

    if env.get("GRIDOS_REQUIRE_API_KEY", "").lower() != "true":
        issues.append("GRIDOS_REQUIRE_API_KEY must be true in production.")

    api_keys = env.get("GRIDOS_API_KEYS", "")
    if "replace-with" in api_keys or not api_keys:
        issues.append("GRIDOS_API_KEYS contains placeholder or is empty.")
    else:
        for pair in [item.strip() for item in api_keys.split(",") if item.strip()]:
            if ":" not in pair:
                issues.append(f"Invalid API key entry format: {pair}")
                continue
            principal, token = pair.split(":", maxsplit=1)
            if len(token) < 24:
                issues.append(f"API key for '{principal}' is too short.")

    rate = env.get("GRIDOS_RATE_LIMIT_PER_MINUTE", "")
    if not rate.isdigit() or int(rate) < 60:
        issues.append("GRIDOS_RATE_LIMIT_PER_MINUTE should be an integer >= 60.")

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate GridOS production env file.")
    parser.add_argument("--env-file", default=".env", help="Path to env file to validate.")
    args = parser.parse_args()

    path = Path(args.env_file)
    if not path.exists():
        raise SystemExit(f"Env file not found: {path}")

    env = parse_env(path)
    issues = validate(env)
    if issues:
        print("Production env validation failed:")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)

    print("Production env validation passed.")


if __name__ == "__main__":
    main()
