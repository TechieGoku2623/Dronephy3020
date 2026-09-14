# GridOS-Logic v2.0 (Dronephy3020)

Full-stack platform for autonomous power-line inspection drones that can perch and recharge from energized lines while staying under human command authority.

## What is implemented

### Backend (FastAPI)
- Strict Pydantic v2 domain models (`app/models.py`)
- Physics engine (`app/physics_engine.py`)
  - IEEE 738-style thermal estimate for conductor heating
  - Biot-Savart magnetic field estimate at 0.05m clamp distance
  - Harmonic angle optimizer with corona-risk guardrail
- Weather overwrite and async weather validator (`app/weather_service.py`)
  - Automatic lockout if wind > 15 m/s or heavy precipitation
- Geospatial routing core (`app/routing_engine.py`)
  - Haversine distance
  - Battery-constrained routing
  - Safety-first filtering
  - Multi-variable score:
    - `score = (magnetic field / (distance + 0.1)) * memory_multiplier`
- Human control authority (`app/human_control.py`)
  - Emergency grounding lockout
  - Force-segment command with safety checks
- Self-adapting memory (`app/memory_engine.py`)
  - Drone-specific learning from success/failure outcomes
  - Charge-rate EMA and bounded scoring influence
- API routes (`app/main.py`)
  - `POST /api/v1/routing/next-perch`
  - `GET /api/v1/grid/segments`
  - `POST /api/v1/weather/override`
  - `POST /api/v1/control/command`
  - `POST /api/v1/memory/feedback`
  - `GET /api/v1/system/state`

### Frontend (React + Vite)
- Dynamic dashboard (`src/App.js`, `src/components/Dashboard.jsx`)
  - Real-time segment vector map with status colors
  - Live telemetry marker
  - Safety/induction metrics
  - Interactive weather override controls
  - Human command panel
  - Memory feedback actions for online learning

### Quality and orchestration
- Test suite (`test_backend.py`) covering:
  - Safety overrides
  - Haversine metrics
  - Harmonic edge cases
  - Memory adaptation and human control
- Runtime dependencies (`requirements.txt`)
- One-command flow (`run.sh`) to:
  1. Run tests
  2. Start backend
  3. Start frontend

## Why these advancements were added

You asked to add self-adapting memory, human control, and extra advancements informed by industry difficulties. This code includes:

1. **Self-adapting memory**
   - Drones learn segment success history and observed charge quality.
   - Improves repeat mission reliability over time.

2. **Human command authority**
   - Operators can immediately ground all drones (emergency lockout).
   - Operators can force specific segments when required by operations.

3. **Weather API overwrite**
   - Weather is treated as a first-class safety blocker, not an afterthought.
   - Quadrant-level overrides let control rooms simulate and enforce micro-climate decisions.

4. **Transparent rationale output**
   - Recommendations include rationale strings for post-flight audit and regulator review.

## Industry challenges used in design decisions

This architecture explicitly responds to common challenges seen across major drone operators:

- **Weather volatility (seen broadly in delivery fleets such as Zipline-type operations):**
  - Mitigation: async weather checks + hard lockout + operator weather overrides.

- **Regulatory pressure for auditable safety and human oversight (common in Prime Air/BVLOS expansion discussions):**
  - Mitigation: explicit human override layer and safety rationale in every recommendation.

- **Battery/range bottlenecks and charging uncertainty (common in delivery and line-inspection fleets):**
  - Mitigation: battery-safe range filtering + induction score + adaptive memory for better charging segment selection.

- **Power-line landing/perching risk under harmonics and wind (observed in in-contact inspection research):**
  - Mitigation: harmonic clamp-angle optimization + corona risk threshold + thermal and induction safety checks.

## Quick start

```bash
python -m pip install -r requirements.txt
./run.sh
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
