<div align="center">

# GridOS-Logic v2.0

### Dronephy3020

**Safe next-perch decisions for power-line inspection drones**

Inspection drones that land on live conductors to recharge cannot pick the closest span. They need a defendable next perch — physics, weather, battery, memory, maintenance, and a human who can always override.

[![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)](#quick-start)
[![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=black)](#quick-start)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](#quick-start)
[![Demo](https://img.shields.io/badge/Demo-plays%20on%20this%20page-00D1FF)](#watch-the-demo)

</div>

---

## The problem

A perch that looks convenient can still be the wrong landing.

| What goes wrong in the field | Why “closest span” fails |
| --- | --- |
| Hot or overloaded conductor | Thermal limit exceeded |
| Weak magnetic coupling | Induction too low to charge |
| Wind, rain, or icing | Autonomy should stop, not improvise |
| Harmonic / worn clamp sites | Silent asset wear |
| Battery fade | Range that used to be safe is not |

Without a written rationale, operators cannot audit why the aircraft landed where it did — and they cannot force a corridor or ground the fleet when conditions change.

## What this software does

GridOS answers one operational question:

> Given this drone’s battery, this weather, and this grid, **which span is safe to land on next — and why?**

The dashboard is a live React client on a FastAPI physics stack. Segment color is a **safety state**, not decoration. Apply heavy precipitation and the grid goes red: next perch becomes `NO_SAFE_SEGMENT`. A human can still force a span or declare an emergency lockout.

---

## Watch the demo

The walkthrough **plays on this page**. It is the real dashboard talking to the API — not a mockup.

<p align="center">
  <img src="docs/demo.gif" alt="GridOS dashboard walkthrough — plays inline" width="920"/>
</p>

| In the clip | Why it matters |
| --- | --- |
| Header metrics | Fleet, thermal safety, induction, maintenance watch |
| Vector grid | Green = safe to perch |
| Weather override | Autonomy stops when weather lockout fires |
| Human command | Operator authority always wins |
| Successful perch | Memory of which spans actually charged |
| Anomaly forecast | Routing avoids degrading assets unless forced |

---

## How it solves the problem

```text
Grid telemetry
    → physics (heat, induction, corona, clamp angle)
    → weather lockout
    → battery-safe range
    → memory of past perches
    → predictive maintenance penalty
    → human override (always wins)
    → next perch + written rationale
```

| Layer | Code | Role |
| --- | --- | --- |
| Physics | `app/physics_engine.py` | IEEE 738-style heating, Biot–Savart induction at 0.05 m, harmonic clamp angle, corona guardrail |
| Weather | `app/weather_service.py` | Lockout if wind > 15 m/s or heavy precipitation |
| Routing | `app/routing_engine.py` | Haversine + battery filter; score ≈ `(B / (distance + 0.1)) × memory × maintenance` |
| Human | `app/human_control.py` | Emergency grounding; force-segment with safety checks |
| Memory | `app/memory_engine.py` | Per-drone success ratio and charge-rate EMA |
| Maintenance | `app/maintenance_engine.py` | Battery-drain and span-wear; CRITICAL spans skipped unless forced |
| Dashboard | `src/components/Dashboard.jsx` | Live map, controls, anomaly list |

The grid in this repo is a **seeded in-memory model** (SF Bay–style spans), not a live utility SCADA feed. Physics modules are compact engineering approximations, not full FEM.

```text
dronephy3020/
├── app/                         FastAPI
│   ├── main.py
│   ├── physics_engine.py
│   ├── routing_engine.py
│   ├── weather_service.py
│   ├── human_control.py
│   ├── memory_engine.py
│   └── maintenance_engine.py
├── src/                         React + Vite dashboard
├── docs/demo.gif
├── test_backend.py
├── requirements.txt
├── package.json
└── run.sh                       tests → API :8000 → UI :3000
```

---

## Quick start

```bash
python -m pip install -r requirements.txt
npm install
./run.sh
```

| Surface | URL |
| --- | --- |
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |

Optional: `WEATHER_API_BASE` for live weather; otherwise segment wind and operator override apply. The UI uses `VITE_API_BASE` (default `http://localhost:8000`).

### Example: next perch

```bash
curl -s http://localhost:8000/api/v1/routing/next-perch \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "DRONE-001",
    "latitude": 37.7712,
    "longitude": -122.4444,
    "battery_percentage": 76.0,
    "consumption_rate_per_min": 1.1
  }'
```

Teach memory from a real landing with `POST /api/v1/memory/feedback`. Force a span or ground the fleet with `POST /api/v1/control/command`.

---

<p align="center"><sub>GridOS · perch only when physics, weather, memory, and a human all allow it</sub></p>
