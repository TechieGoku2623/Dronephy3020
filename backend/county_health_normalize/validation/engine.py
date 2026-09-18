"""Validation engine: map source rows, validate against the canonical schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd
import pandera.errors as pa_errors

from county_health_normalize.mapper.column_mapper import ColumnMapper, MappingError
from county_health_normalize.mapper.config import SourceMappingConfig
from county_health_normalize.schema.canonical import (
    AGE_BRACKETS,
    CONDITION_CATEGORIES,
    SEVERITIES,
    CaseRecordSchema,
)


@dataclass
class RowValidationResult:
    """Per-row pass/fail outcome with concrete failure reasons."""

    row_number: int  # 1-based index in the source file (header excluded)
    passed: bool
    data: dict[str, Any] | None = None
    failures: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregate result of validating one source file / batch."""

    source_system: str
    total_rows: int
    passed_count: int
    failed_count: int
    rows: list[RowValidationResult]
    mapping_error: str | None = None

    @property
    def passed_rows(self) -> list[RowValidationResult]:
        return [r for r in self.rows if r.passed]

    @property
    def failed_rows(self) -> list[RowValidationResult]:
        return [r for r in self.rows if not r.passed]


class ValidationEngine:
    """Apply a source mapper, then validate each row against CaseRecordSchema."""

    def __init__(self, config: SourceMappingConfig):
        self.config = config
        self.mapper = ColumnMapper(config)

    def validate(
        self,
        raw_df: pd.DataFrame,
        *,
        ingested_at: datetime | None = None,
    ) -> ValidationReport:
        """Map and validate a raw DataFrame; never silently drops rows."""
        try:
            mapped_df = self.mapper.map_dataframe(raw_df, ingested_at=ingested_at)
        except MappingError as exc:
            return ValidationReport(
                source_system=self.config.source_system,
                total_rows=len(raw_df),
                passed_count=0,
                failed_count=len(raw_df),
                rows=[],
                mapping_error=str(exc),
            )

        if mapped_df.empty:
            return ValidationReport(
                source_system=self.config.source_system,
                total_rows=0,
                passed_count=0,
                failed_count=0,
                rows=[],
            )

        # Collect duplicate case_ids across the whole batch (after mapping).
        duplicate_ids = self._duplicate_case_ids(mapped_df)

        row_results: list[RowValidationResult] = []
        for position, (_, row) in enumerate(mapped_df.iterrows(), start=1):
            failures = self._validate_row(row, duplicate_ids=duplicate_ids)
            if failures:
                row_results.append(
                    RowValidationResult(
                        row_number=position,
                        passed=False,
                        data=self._row_to_serializable(row),
                        failures=failures,
                    )
                )
            else:
                # Confirm with Pandera on a single-row frame for coerce/type safety.
                single = mapped_df.iloc[[position - 1]].copy()
                try:
                    validated = CaseRecordSchema.validate(single, lazy=True)
                    payload = self._row_to_serializable(validated.iloc[0])
                    row_results.append(
                        RowValidationResult(
                            row_number=position,
                            passed=True,
                            data=payload,
                            failures=[],
                        )
                    )
                except (pa_errors.SchemaErrors, pa_errors.SchemaError) as exc:
                    row_results.append(
                        RowValidationResult(
                            row_number=position,
                            passed=False,
                            data=self._row_to_serializable(row),
                            failures=self._schema_error_messages(exc, position),
                        )
                    )

        passed_count = sum(1 for r in row_results if r.passed)
        return ValidationReport(
            source_system=self.config.source_system,
            total_rows=len(row_results),
            passed_count=passed_count,
            failed_count=len(row_results) - passed_count,
            rows=row_results,
        )

    def _validate_row(self, row: pd.Series, *, duplicate_ids: set[str]) -> list[str]:
        """Return human-readable failure reasons for a mapped row (pre-Pandera)."""
        failures: list[str] = []

        case_id = row.get("case_id")
        if case_id is None or (isinstance(case_id, float) and pd.isna(case_id)) or str(case_id).strip() == "":
            failures.append("case_id: required field is missing")
        else:
            case_id_str = str(case_id).strip()
            if case_id_str in duplicate_ids:
                failures.append(f"case_id: duplicate value '{case_id_str}' within this batch")

        report_date = row.get("report_date")
        if report_date is None or (isinstance(report_date, float) and pd.isna(report_date)):
            failures.append("report_date: missing or could not be parsed with configured date formats")
        elif not isinstance(report_date, date):
            failures.append(f"report_date: invalid date value '{report_date}'")

        zip_code = row.get("zip_code")
        if zip_code is None or (isinstance(zip_code, float) and pd.isna(zip_code)) or str(zip_code).strip() == "":
            failures.append("zip_code: required field is missing")
        else:
            zip_str = str(zip_code).strip()
            if not zip_str.isdigit() or len(zip_str) != 5:
                failures.append(f"zip_code: must be a 5-digit ZIP code, got '{zip_str}'")

        condition = row.get("condition_category")
        if condition is None or (isinstance(condition, float) and pd.isna(condition)) or str(condition).strip() == "":
            failures.append("condition_category: required field is missing")
        elif str(condition) not in CONDITION_CATEGORIES:
            failures.append(
                f"condition_category: '{condition}' is not an allowed value "
                f"({', '.join(CONDITION_CATEGORIES)})"
            )

        age = row.get("age_bracket")
        if age is None or (isinstance(age, float) and pd.isna(age)) or str(age).strip() == "":
            failures.append("age_bracket: required field is missing")
        elif str(age) not in AGE_BRACKETS:
            failures.append(
                f"age_bracket: '{age}' is not an allowed value ({', '.join(AGE_BRACKETS)})"
            )

        severity = row.get("severity")
        if severity is None or (isinstance(severity, float) and pd.isna(severity)) or str(severity).strip() == "":
            failures.append("severity: required field is missing")
        elif str(severity) not in SEVERITIES:
            failures.append(
                f"severity: '{severity}' is not an allowed value ({', '.join(SEVERITIES)})"
            )

        source_system = row.get("source_system")
        if source_system is None or str(source_system).strip() == "":
            failures.append("source_system: required field is missing")

        ingested_at = row.get("ingested_at")
        if ingested_at is None or (isinstance(ingested_at, float) and pd.isna(ingested_at)):
            failures.append("ingested_at: required field is missing")

        return failures

    @staticmethod
    def _duplicate_case_ids(mapped_df: pd.DataFrame) -> set[str]:
        series = mapped_df["case_id"].dropna().astype(str).str.strip()
        series = series[series != ""]
        counts = series.value_counts()
        return set(counts[counts > 1].index.tolist())

    @staticmethod
    def _row_to_serializable(row: pd.Series) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in row.items():
            key_str = str(key)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                payload[key_str] = None
            elif key_str == "report_date" and isinstance(value, (datetime, date, pd.Timestamp)):
                # Always expose report_date as YYYY-MM-DD (date, not datetime).
                if isinstance(value, pd.Timestamp):
                    payload[key_str] = value.date().isoformat()
                elif isinstance(value, datetime):
                    payload[key_str] = value.date().isoformat()
                else:
                    payload[key_str] = value.isoformat()
            elif isinstance(value, pd.Timestamp):
                payload[key_str] = value.isoformat()
            elif isinstance(value, datetime):
                payload[key_str] = value.isoformat()
            elif isinstance(value, date):
                payload[key_str] = value.isoformat()
            else:
                payload[key_str] = value
        return payload

    @staticmethod
    def _schema_error_messages(exc: Exception, row_number: int) -> list[str]:
        messages: list[str] = []
        failure_cases = getattr(exc, "failure_cases", None)
        if failure_cases is not None and not failure_cases.empty:
            for _, case in failure_cases.iterrows():
                column = case.get("column", "unknown")
                check = case.get("check", "failed check")
                messages.append(f"{column}: {check}")
        if not messages:
            messages.append(str(exc))
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for msg in messages:
            if msg not in seen:
                seen.add(msg)
                unique.append(msg)
        return unique or [f"row {row_number}: schema validation failed"]
