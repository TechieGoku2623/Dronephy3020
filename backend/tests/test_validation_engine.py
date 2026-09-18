"""Unit tests for Phase 1 — mapping + validation engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from county_health_normalize.config import load_bundled_source_config, list_source_configs
from county_health_normalize.mapper import ColumnMapper, MappingError, load_source_config
from county_health_normalize.validation import ValidationEngine

FIXTURE_INGESTED_AT = datetime(2026, 3, 15, 12, 0, 0)
SOURCES_DIR = (
    Path(__file__).resolve().parents[1]
    / "county_health_normalize"
    / "config"
    / "sources"
)


@pytest.fixture
def lab_config():
    return load_bundled_source_config("county_central_lab")


@pytest.fixture
def clinic_config():
    return load_bundled_source_config("community_clinic_ehr")


@pytest.fixture
def ems_config():
    return load_bundled_source_config("ems_cad_export")


def test_three_example_source_configs_exist_and_load():
    configs = list_source_configs()
    assert len(configs) == 3
    stems = {p.stem for p in configs}
    assert stems == {"county_central_lab", "community_clinic_ehr", "ems_cad_export"}
    for path in configs:
        cfg = load_source_config(path)
        assert cfg.source_system == path.stem
        assert "case_id" in cfg.columns
        assert "report_date" in cfg.columns


def test_correct_mapping_lab_us_dates(lab_config):
    raw = pd.DataFrame(
        [
            {
                "Accession Number": "LAB-1001",
                "Specimen Collection Date": "03/01/2026",
                "Patient ZIP Code": "97201",
                "Disease Category": "Influenza",
                "Age Band": "18 to 49",
                "Clinical Severity": "Mild",
            },
            {
                "Accession Number": "LAB-1002",
                "Specimen Collection Date": "03/02/26",
                "Patient ZIP Code": "97202-1234",
                "Disease Category": "West Nile",
                "Age Band": "65 and older",
                "Clinical Severity": "Critical / ICU",
            },
        ]
    )
    mapped = ColumnMapper(lab_config).map_dataframe(raw, ingested_at=FIXTURE_INGESTED_AT)

    assert list(mapped.columns) == [
        "case_id",
        "report_date",
        "zip_code",
        "condition_category",
        "age_bracket",
        "severity",
        "source_system",
        "ingested_at",
    ]
    assert mapped.iloc[0]["case_id"] == "LAB-1001"
    assert mapped.iloc[0]["report_date"].isoformat() == "2026-03-01"
    assert mapped.iloc[0]["condition_category"] == "respiratory"
    assert mapped.iloc[0]["age_bracket"] == "18-49"
    assert mapped.iloc[0]["severity"] == "mild"
    assert mapped.iloc[1]["zip_code"] == "97202"
    assert mapped.iloc[1]["condition_category"] == "vector_borne"
    assert mapped.iloc[1]["severity"] == "critical"
    assert mapped.iloc[0]["source_system"] == "county_central_lab"


def test_correct_mapping_clinic_iso_dates(clinic_config):
    raw = pd.DataFrame(
        [
            {
                "case_id": "CLN-9",
                "encounter_date": "2026-01-15",
                "patient_zip": "10001",
                "condition_category": "gastrointestinal",
                "age_bracket": "5-17",
                "severity": "moderate",
            }
        ]
    )
    report = ValidationEngine(clinic_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.passed_count == 1
    assert report.failed_count == 0
    assert report.rows[0].data["report_date"] == "2026-01-15"
    assert report.rows[0].data["condition_category"] == "gastrointestinal"


def test_correct_mapping_ems_dob_column_and_coded_values(ems_config):
    """EMS config maps legacy 'DOB' column name to report_date with DD/MM/YYYY."""
    raw = pd.DataFrame(
        [
            {
                "INC_ID": "EMS-77",
                "DOB": "15/02/2026",
                "ZIP5": "98101",
                "CAT": "R",
                "AGE_GRP": "C",
                "SEV": "2",
            }
        ]
    )
    report = ValidationEngine(ems_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.mapping_error is None
    assert report.passed_count == 1
    row = report.rows[0]
    assert row.passed
    assert row.data["report_date"] == "2026-02-15"
    assert row.data["condition_category"] == "respiratory"
    assert row.data["age_bracket"] == "18-49"
    assert row.data["severity"] == "moderate"


def test_missing_required_fields(lab_config):
    raw = pd.DataFrame(
        [
            {
                "Accession Number": "LAB-2001",
                "Specimen Collection Date": "03/01/2026",
                "Patient ZIP Code": "97201",
                "Disease Category": "Influenza",
                "Age Band": "NA",  # missing via configured token
                "Clinical Severity": "",  # missing blank
            }
        ]
    )
    report = ValidationEngine(lab_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.passed_count == 0
    assert report.failed_count == 1
    reasons = " | ".join(report.rows[0].failures)
    assert "age_bracket: required field is missing" in reasons
    assert "severity: required field is missing" in reasons


def test_missing_required_column_raises_mapping_error(lab_config):
    raw = pd.DataFrame(
        [
            {
                "Accession Number": "LAB-2002",
                "Specimen Collection Date": "03/01/2026",
                # Patient ZIP Code intentionally omitted
                "Disease Category": "Influenza",
                "Age Band": "Under 5",
                "Clinical Severity": "Mild",
            }
        ]
    )
    with pytest.raises(MappingError, match="Patient ZIP Code"):
        ColumnMapper(lab_config).map_dataframe(raw)

    report = ValidationEngine(lab_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.mapping_error is not None
    assert "Patient ZIP Code" in report.mapping_error
    assert report.passed_count == 0


def test_malformed_dates(lab_config):
    raw = pd.DataFrame(
        [
            {
                "Accession Number": "LAB-3001",
                "Specimen Collection Date": "not-a-date",
                "Patient ZIP Code": "97201",
                "Disease Category": "Influenza",
                "Age Band": "Under 5",
                "Clinical Severity": "Mild",
            },
            {
                "Accession Number": "LAB-3002",
                "Specimen Collection Date": "2026-03-01",  # ISO — not in lab date_formats
                "Patient ZIP Code": "97201",
                "Disease Category": "Influenza",
                "Age Band": "Under 5",
                "Clinical Severity": "Mild",
            },
        ]
    )
    # Lab config only lists MM/DD/YYYY; ISO may still parse via pandas fallback.
    # Force a clearly unparseable value on row 0; row 1 uses a valid US format.
    raw.loc[1, "Specimen Collection Date"] = "13/40/2026"

    report = ValidationEngine(lab_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.failed_count == 2
    assert report.passed_count == 0
    for row in report.rows:
        assert any("report_date" in f for f in row.failures)


def test_duplicate_case_ids(clinic_config):
    raw = pd.DataFrame(
        [
            {
                "case_id": "DUP-1",
                "encounter_date": "2026-01-01",
                "patient_zip": "10001",
                "condition_category": "other",
                "age_bracket": "18-49",
                "severity": "mild",
            },
            {
                "case_id": "DUP-1",
                "encounter_date": "2026-01-02",
                "patient_zip": "10002",
                "condition_category": "respiratory",
                "age_bracket": "50-64",
                "severity": "severe",
            },
            {
                "case_id": "DUP-2",
                "encounter_date": "2026-01-03",
                "patient_zip": "10003",
                "condition_category": "other",
                "age_bracket": "0-4",
                "severity": "mild",
            },
        ]
    )
    report = ValidationEngine(clinic_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.total_rows == 3
    assert report.passed_count == 1
    assert report.failed_count == 2

    failed = {r.row_number: r for r in report.failed_rows}
    assert 1 in failed and 2 in failed
    assert any("duplicate" in f for f in failed[1].failures)
    assert any("duplicate" in f for f in failed[2].failures)
    assert report.rows[2].passed is True
    assert report.rows[2].data["case_id"] == "DUP-2"


def test_invalid_zip_and_unknown_category(lab_config):
    raw = pd.DataFrame(
        [
            {
                "Accession Number": "LAB-4001",
                "Specimen Collection Date": "03/01/2026",
                "Patient ZIP Code": "97",  # too short
                "Disease Category": "Unmapped Disease",
                "Age Band": "Under 5",
                "Clinical Severity": "Mild",
            }
        ]
    )
    report = ValidationEngine(lab_config).validate(raw, ingested_at=FIXTURE_INGESTED_AT)
    assert report.failed_count == 1
    reasons = " | ".join(report.rows[0].failures)
    assert "zip_code" in reasons
    assert "condition_category" in reasons


def test_config_rejects_unknown_canonical_field():
    with pytest.raises(ValueError, match="Unknown canonical field"):
        load_source_config_from_bad_field()


def load_source_config_from_bad_field():
    from county_health_normalize.mapper.config import load_source_config_from_dict

    return load_source_config_from_dict(
        {
            "source_system": "bad",
            "columns": {
                "case_id": {"source": "id"},
                "report_date": {"source": "dt", "date_formats": ["%Y-%m-%d"]},
                "zip_code": {"source": "zip"},
                "condition_category": {"source": "cat"},
                "age_bracket": {"source": "age"},
                "severity": {"source": "sev"},
                "patient_name": {"source": "name"},  # not in canonical schema
            },
        }
    )
