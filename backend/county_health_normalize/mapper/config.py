"""YAML-driven source mapping configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from county_health_normalize.schema.canonical import CANONICAL_FIELDS

# Fields supplied by the pipeline rather than the source CSV.
PIPELINE_SUPPLIED_FIELDS = frozenset({"source_system", "ingested_at"})

# Fields that must be mapped from the source file.
REQUIRED_MAPPED_FIELDS = tuple(
    f for f in CANONICAL_FIELDS if f not in PIPELINE_SUPPLIED_FIELDS
)


@dataclass(frozen=True)
class FieldMapping:
    """How one canonical field is derived from a source column."""

    source: str
    date_formats: tuple[str, ...] = ()
    value_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldMapping:
        if "source" not in data or not str(data["source"]).strip():
            raise ValueError("Each column mapping requires a non-empty 'source' column name")

        date_formats_raw = data.get("date_formats") or data.get("date_format") or []
        if isinstance(date_formats_raw, str):
            date_formats: tuple[str, ...] = (date_formats_raw,)
        else:
            date_formats = tuple(str(fmt) for fmt in date_formats_raw)

        value_map_raw = data.get("value_map") or {}
        if not isinstance(value_map_raw, dict):
            raise ValueError("'value_map' must be a mapping of source value -> canonical value")

        return cls(
            source=str(data["source"]).strip(),
            date_formats=date_formats,
            value_map={str(k): str(v) for k, v in value_map_raw.items()},
        )


@dataclass(frozen=True)
class SourceMappingConfig:
    """Config-driven mapping from one data source's CSV layout to the canonical schema."""

    source_system: str
    description: str
    columns: dict[str, FieldMapping]
    missing_values: tuple[str, ...] = ("", "NA", "N/A", "NULL", "null", "-", ".")

    def mapped_source_columns(self) -> dict[str, str]:
        """Return canonical_field -> raw column name."""
        return {field_name: mapping.source for field_name, mapping in self.columns.items()}


def load_source_config_from_dict(data: dict[str, Any]) -> SourceMappingConfig:
    """Parse and validate a source mapping config dictionary."""
    if not isinstance(data, dict):
        raise ValueError("Source config must be a mapping")

    source_system = str(data.get("source_system") or "").strip()
    if not source_system:
        raise ValueError("source_system is required")

    description = str(data.get("description") or "").strip()
    columns_raw = data.get("columns")
    if not isinstance(columns_raw, dict) or not columns_raw:
        raise ValueError("columns must be a non-empty mapping of canonical field -> mapping rules")

    columns: dict[str, FieldMapping] = {}
    for field_name, field_data in columns_raw.items():
        if field_name not in CANONICAL_FIELDS:
            raise ValueError(
                f"Unknown canonical field '{field_name}'. "
                f"Allowed: {', '.join(CANONICAL_FIELDS)}"
            )
        if field_name in PIPELINE_SUPPLIED_FIELDS:
            raise ValueError(
                f"Field '{field_name}' is set by the pipeline and must not be mapped from CSV"
            )
        if not isinstance(field_data, dict):
            raise ValueError(f"Mapping for '{field_name}' must be a mapping")
        columns[field_name] = FieldMapping.from_dict(field_data)

    missing = [f for f in REQUIRED_MAPPED_FIELDS if f not in columns]
    if missing:
        raise ValueError(
            "Source config is missing required field mappings: " + ", ".join(missing)
        )

    missing_values_raw = data.get("missing_values")
    if missing_values_raw is None:
        missing_values = ("", "NA", "N/A", "NULL", "null", "-", ".")
    else:
        if not isinstance(missing_values_raw, list):
            raise ValueError("missing_values must be a list of strings")
        missing_values = tuple(str(v) for v in missing_values_raw)

    return SourceMappingConfig(
        source_system=source_system,
        description=description,
        columns=columns,
        missing_values=missing_values,
    )


def load_source_config(path: str | Path) -> SourceMappingConfig:
    """Load a YAML source mapping config from disk."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        raise ValueError(f"Config file is empty: {config_path}")
    return load_source_config_from_dict(data)
