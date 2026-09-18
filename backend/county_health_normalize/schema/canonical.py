"""Canonical case-record schema used across ingestion and validation."""

from __future__ import annotations

from typing import Final

import pandera as pa

# Controlled vocabularies for standardized fields.
CONDITION_CATEGORIES: Final[tuple[str, ...]] = (
    "respiratory",
    "gastrointestinal",
    "vector_borne",
    "vaccine_preventable",
    "other",
)

AGE_BRACKETS: Final[tuple[str, ...]] = (
    "0-4",
    "5-17",
    "18-49",
    "50-64",
    "65+",
)

SEVERITIES: Final[tuple[str, ...]] = (
    "mild",
    "moderate",
    "severe",
    "critical",
)

CANONICAL_FIELDS: Final[tuple[str, ...]] = (
    "case_id",
    "report_date",
    "zip_code",
    "condition_category",
    "age_bracket",
    "severity",
    "source_system",
    "ingested_at",
)


def build_case_record_schema() -> pa.DataFrameSchema:
    """Pandera schema for a normalized case record.

    Fields match the product canonical schema exactly — do not add fields
    without an explicit product decision.
    """
    return pa.DataFrameSchema(
        {
            "case_id": pa.Column(
                str,
                nullable=False,
                unique=True,
                checks=pa.Check.str_length(min_value=1),
            ),
            "report_date": pa.Column("datetime64[ns]", nullable=False),
            "zip_code": pa.Column(
                str,
                nullable=False,
                checks=pa.Check.str_matches(r"^\d{5}$"),
            ),
            "condition_category": pa.Column(
                str,
                nullable=False,
                checks=pa.Check.isin(list(CONDITION_CATEGORIES)),
            ),
            "age_bracket": pa.Column(
                str,
                nullable=False,
                checks=pa.Check.isin(list(AGE_BRACKETS)),
            ),
            "severity": pa.Column(
                str,
                nullable=False,
                checks=pa.Check.isin(list(SEVERITIES)),
            ),
            "source_system": pa.Column(
                str,
                nullable=False,
                checks=pa.Check.str_length(min_value=1),
            ),
            "ingested_at": pa.Column("datetime64[ns]", nullable=False),
        },
        strict=True,
        coerce=True,
    )


# Module-level singleton used by the validation engine.
CaseRecordSchema = build_case_record_schema()
