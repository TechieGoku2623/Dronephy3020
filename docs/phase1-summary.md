# Phase 1 — Canonical schema + validation engine

## Delivered

1. **Canonical Pandera schema** (`CaseRecordSchema`) with exactly these fields:
   - `case_id`, `report_date`, `zip_code`, `condition_category`, `age_bracket`, `severity`, `source_system`, `ingested_at`
2. **YAML source mapper** — each data source has a config that maps raw column names, date formats, missing-value tokens, and optional value maps onto the canonical fields. No per-source logic in Python.
3. **Validation engine** — maps a DataFrame, then returns per-row pass/fail with specific failure reasons (missing fields, bad dates, bad ZIP, invalid categories, duplicate `case_id`s). Mapping-level errors (missing columns) are reported without silently dropping rows.
4. **Three example configs** with different conventions (lab / clinic EHR / EMS).
5. **Unit tests** covering correct mapping, missing required fields, malformed dates, and duplicate case IDs.

## Controlled vocabularies (for mapped categorical fields)

| Field | Allowed values |
| --- | --- |
| `condition_category` | respiratory, gastrointestinal, vector_borne, vaccine_preventable, other |
| `age_bracket` | 0-4, 5-17, 18-49, 50-64, 65+ |
| `severity` | mild, moderate, severe, critical |

These are constraints on the existing canonical fields, not new fields.

## Out of scope until later phases

Ingestion API, Postgres, frontend, auth, Docker Compose.
