# GridOS-Logic v2.1 SaaS Release (Dronephy3020)

GridOS-Logic is a full-stack command-and-routing platform for autonomous grid-living drones that perch on energized lines for recharge. This release upgrades the project to SaaS-ready architecture with tenant isolation, auth, rate limiting, deployment packaging, and CI.

## Core platform capabilities

### Autonomous routing and safety
- Strict Pydantic v2 models (`app/models.py`)
- Physics intelligence (`app/physics_engine.py`)
  - IEEE 738-style thermal safety checks
  - Biot-Savart magnetic induction estimation at `r=0.05m`
  - THD-driven harmonic clamp-angle optimization
  - Safety states:
    - `SAFE`
    - `UNSAFE_OVERHEATING`
    - `UNSAFE_LOW_INDUCTION`
    - `UNSAFE_CORONA_RISK`
    - `UNSAFE_WEATHER_LOCKOUT`
- Geospatial ranking (`app/routing_engine.py`)
  - Haversine distance
  - Battery-safe range filtering
  - Score formula:
    - `score = (magnetic_field / (distance + 0.1)) * memory_multiplier`

### Operational intelligence
- Asynchronous weather service (`app/weather_service.py`)
  - External weather API support
  - Manual weather overwrite lockouts
- Human command authority (`app/human_control.py`)
  - Emergency grounding lockout
  - Force-segment routing override
- Self-adapting memory (`app/memory_engine.py`)
  - Per-drone/per-segment learning
  - Success ratio + charge-rate EMA feedback loop

## SaaS release-level upgrades

### 1) Multi-tenant runtime isolation
- `app/tenant_runtime.py`
- Each tenant gets isolated:
  - weather overrides
  - human control state
  - adaptive memory profile

### 2) Security hardening
- `app/security.py`
- Header-based access controls:
  - `X-Tenant-ID`
  - `X-API-Key` (production-required when enabled)
- Configurable strictness for tenant enforcement and API keys.

### 3) Environment-driven config
- `app/config.py`
- Environment variables control:
  - CORS origins
  - API key policies
  - tenant defaults
  - rate limits
  - logging level

### 4) API protection and observability
- `app/rate_limiter.py`
- Fixed-window per-tenant/per-principal rate limiting
- Request middleware adds:
  - request ID (`X-Request-ID`)
  - request timing logs
  - rate-limit headers

### 5) Ops and health endpoints
- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/system/release`

## API surface

Core endpoints (tenant-aware):
- `POST /api/v1/routing/next-perch`
- `GET /api/v1/grid/segments`
- `POST /api/v1/weather/override`
- `DELETE /api/v1/weather/override/{quadrant}`
- `POST /api/v1/control/command`
- `DELETE /api/v1/control/command`
- `POST /api/v1/memory/feedback`
- `POST /api/v1/memory/reset/{drone_id}`
- `GET /api/v1/system/state`

## Frontend (React + Vite)

`src/components/Dashboard.jsx` provides:
- live vector grid and telemetry rendering
- real-time safety/induction metrics
- weather simulation controls
- human command controls
- memory feedback controls
- tenant + API key header controls for SaaS mode

## Production configuration

Generate a secure `.env` automatically:

```bash
python3 scripts/generate_production_env.py \
  --domain app.yourdomain.com \
  --tenant-id yourtenant \
  --output .env
python3 scripts/validate_production_env.py --env-file .env
```

Important variables:
- `GRIDOS_REQUIRE_API_KEY=true`
- `GRIDOS_API_KEYS=ops:<token1>,monitor:<token2>`
- `GRIDOS_ENFORCE_TENANT_HEADER=true`
- `GRIDOS_CORS_ORIGINS=https://app.example.com`
- `GRIDOS_RATE_LIMIT_PER_MINUTE=240`

## Local run

```bash
python3 -m pip install -r requirements.txt
npm install
./run.sh
```

- API: `http://localhost:8000`
- Dashboard: `http://localhost:3000`

Production API process (without Docker):

```bash
source .env
./scripts/run_production_api.sh
```

## Dockerized SaaS deployment

```bash
docker compose up --build
```

Containers:
- `gridos-api` on port `8000`
- `gridos-web` on port `3000`

## CI

GitHub Actions workflow (`.github/workflows/ci.yml`) runs:
1. Backend tests (`pytest`)
2. Frontend production build (`vite build`)

## Release checklist

Use `SAAS_RELEASE_CHECKLIST.md` before shipping to production.

## Test coverage focus

`test_backend.py` validates:
- geometric distance correctness
- THD/harmonic safety edge cases
- weather lockout behavior
- human override routing
- hardened API-key behavior
- tenant isolation behavior
