"""Apply YAML source mappings to raw case-report DataFrames."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from county_health_normalize.mapper.config import REQUIRED_MAPPED_FIELDS, SourceMappingConfig


class MappingError(Exception):
    """Raised when a source file cannot be mapped using the provided config."""


class ColumnMapper:
    """Config-driven column mapper — no per-source hardcoding in application code."""

    def __init__(self, config: SourceMappingConfig):
        self.config = config

    def validate_columns_present(self, raw_df: pd.DataFrame) -> None:
        """Ensure every mapped source column exists in the raw frame."""
        missing = []
        for field_name, mapping in self.config.columns.items():
            if mapping.source not in raw_df.columns:
                missing.append(f"{field_name} (expected column '{mapping.source}')")
        if missing:
            raise MappingError(
                "Source file is missing required columns for "
                f"'{self.config.source_system}': " + "; ".join(missing)
            )

    def map_dataframe(
        self,
        raw_df: pd.DataFrame,
        *,
        ingested_at: datetime | None = None,
    ) -> pd.DataFrame:
        """Return a DataFrame with canonical column names and normalized values.

        Date parsing failures and unknown categorical values are left as NaN /
        empty so the validation engine can attach per-row failure reasons.
        """
        self.validate_columns_present(raw_df)

        if ingested_at is None:
            ingested_at = datetime.now(timezone.utc).replace(tzinfo=None)

        missing_tokens = {v.strip().lower() if isinstance(v, str) else v for v in self.config.missing_values}
        # Always treat blank strings as missing.
        missing_tokens.add("")

        rows: list[dict[str, Any]] = []
        for _, raw_row in raw_df.iterrows():
            mapped: dict[str, Any] = {
                "source_system": self.config.source_system,
                "ingested_at": ingested_at,
            }
            for field_name, mapping in self.config.columns.items():
                raw_value = raw_row[mapping.source]
                mapped[field_name] = self._normalize_value(field_name, raw_value, mapping, missing_tokens)
            rows.append(mapped)

        # Preserve original row order; use a stable column order.
        columns = list(REQUIRED_MAPPED_FIELDS) + ["source_system", "ingested_at"]
        return pd.DataFrame(rows, columns=columns)

    def _normalize_value(
        self,
        field_name: str,
        raw_value: Any,
        mapping: Any,
        missing_tokens: set[Any],
    ) -> Any:
        if self._is_missing(raw_value, missing_tokens):
            return None

        if field_name == "report_date":
            return self._parse_date(raw_value, mapping.date_formats)

        text = str(raw_value).strip()

        if mapping.value_map:
            # Case-insensitive lookup against configured keys.
            lowered = {str(k).strip().lower(): v for k, v in mapping.value_map.items()}
            if text.lower() in lowered:
                text = lowered[text.lower()]
            # If not in map, keep original text — validator will reject invalid enums.

        if field_name == "zip_code":
            return self._normalize_zip(text)

        if field_name == "case_id":
            return text

        return text

    @staticmethod
    def _is_missing(value: Any, missing_tokens: set[Any]) -> bool:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return True
        if isinstance(value, str) and value.strip().lower() in missing_tokens:
            return True
        # Also match non-string tokens configured as missing (rare).
        if value in missing_tokens:
            return True
        return False

    @staticmethod
    def _parse_date(value: Any, date_formats: tuple[str, ...]) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, pd.Timestamp):
            if pd.isna(value):
                return None
            return value.date()

        text = str(value).strip()
        formats = date_formats or ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d")
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

        # Last resort: pandas parser (dayfirst=False for US health depts).
        try:
            parsed = pd.to_datetime(text, errors="raise", dayfirst=False)
            if pd.isna(parsed):
                return None
            return parsed.date()
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _normalize_zip(text: str) -> str | None:
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 5:
            return digits[:5]
        if len(digits) > 0:
            # Preserve short zips so validation can report "must be 5 digits".
            return digits
        return None
