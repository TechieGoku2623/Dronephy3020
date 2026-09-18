"""Helpers for locating bundled source mapping configs."""

from __future__ import annotations

from pathlib import Path

from county_health_normalize.mapper.config import SourceMappingConfig, load_source_config

CONFIG_DIR = Path(__file__).resolve().parent / "sources"


def list_source_configs() -> list[Path]:
    return sorted(CONFIG_DIR.glob("*.yaml"))


def load_bundled_source_config(source_system: str) -> SourceMappingConfig:
    path = CONFIG_DIR / f"{source_system}.yaml"
    if not path.exists():
        available = ", ".join(p.stem for p in list_source_configs()) or "(none)"
        raise FileNotFoundError(
            f"No bundled config for source_system '{source_system}'. Available: {available}"
        )
    return load_source_config(path)
