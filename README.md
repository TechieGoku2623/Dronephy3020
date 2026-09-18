# CountyHealthNormalize

Phase status: **Phase 1 complete** (canonical schema + validation engine). Later phases are not started.

## What this is

A local/on-prem tool for small city and county public health departments to clean, standardize, and analyze case-report CSVs from labs, clinics, and EMS.

## Repo layout

```
/backend   Python package + tests (Phase 1+)
/frontend  React app (Phase 4+)
/docs      Design notes and phase summaries
```

## Phase 1 — quick start (validation engine only)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pytest -v
```

Example source mapping configs live in:

`backend/county_health_normalize/config/sources/`

- `county_central_lab.yaml` — verbose headers, MM/DD/YYYY
- `community_clinic_ehr.yaml` — snake_case, ISO dates
- `ems_cad_export.yaml` — cryptic codes, DOB-named date column, DD/MM/YYYY
