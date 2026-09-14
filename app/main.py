"""FastAPI entrypoint for GridOS-Logic v2.0."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.human_control import HumanControlLayer
from app.memory_engine import SelfAdaptingMemory
from app.models import (
    DroneTelemetry,
    HumanControlCommand,
    MissionFeedback,
    PowerLineSegment,
    WeatherOverrideInput,
)
from app.routing_engine import RoutingEngine
from app.weather_service import WeatherService

app = FastAPI(title="GridOS-Logic v2.0", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _seed_segments() -> list[PowerLineSegment]:
    return [
        PowerLineSegment(
            segment_id="SEG-A1",
            lat_start=37.7710,
            lon_start=-122.4470,
            lat_end=37.7740,
            lon_end=-122.4410,
            current_amperage=1250.0,
            ambient_temp_c=32.0,
            wind_speed_ms=8.5,
            total_harmonic_distortion=7.5,
        ),
        PowerLineSegment(
            segment_id="SEG-B3",
            lat_start=37.7650,
            lon_start=-122.4540,
            lat_end=37.7695,
            lon_end=-122.4490,
            current_amperage=800.0,
            ambient_temp_c=28.0,
            wind_speed_ms=5.0,
            total_harmonic_distortion=4.0,
        ),
        PowerLineSegment(
            segment_id="SEG-C5",
            lat_start=37.7790,
            lon_start=-122.4390,
            lat_end=37.7830,
            lon_end=-122.4330,
            current_amperage=1550.0,
            ambient_temp_c=35.0,
            wind_speed_ms=4.5,
            total_harmonic_distortion=10.0,
        ),
        PowerLineSegment(
            segment_id="SEG-D9",
            lat_start=37.7600,
            lon_start=-122.4320,
            lat_end=37.7630,
            lon_end=-122.4270,
            current_amperage=450.0,
            ambient_temp_c=24.0,
            wind_speed_ms=12.0,
            total_harmonic_distortion=3.0,
        ),
    ]


weather_service = WeatherService()
human_control = HumanControlLayer()
memory = SelfAdaptingMemory()
routing_engine = RoutingEngine(_seed_segments(), weather_service, memory, human_control)


@app.post("/api/v1/routing/next-perch")
async def next_perch(telemetry: DroneTelemetry):
    """Compute the safest and highest-yield next perch recommendation."""
    return await routing_engine.recommend_next_perch(telemetry)


@app.get("/api/v1/grid/segments")
async def get_grid_segments():
    """Expose live segment states for the dashboard."""
    return {"segments": await routing_engine.segment_states()}


@app.post("/api/v1/weather/override")
async def set_weather_override(weather_override: WeatherOverrideInput):
    """Apply human-simulated weather control to a specific quadrant."""
    weather_service.apply_override(weather_override)
    return {"ok": True, "quadrant": weather_override.quadrant.upper()}


@app.delete("/api/v1/weather/override/{quadrant}")
async def clear_weather_override(quadrant: str):
    """Clear weather simulation override for one quadrant."""
    weather_service.clear_override(quadrant)
    return {"ok": True, "quadrant": quadrant.upper()}


@app.post("/api/v1/control/command")
async def set_control_command(command: HumanControlCommand):
    """Set operator lockout or force-segment command."""
    state = human_control.update(command)
    return {"ok": True, "state": asdict(state)}


@app.delete("/api/v1/control/command")
async def clear_control_command():
    """Return system to autonomous-only mode."""
    human_control.clear()
    return {"ok": True}


@app.post("/api/v1/memory/feedback")
async def post_mission_feedback(feedback: MissionFeedback):
    """Ingest mission outcome for self-adapting memory updates."""
    memory.register_feedback(feedback)
    return {"ok": True}


@app.post("/api/v1/memory/reset/{drone_id}")
async def reset_memory(drone_id: str):
    """Reset one drone's learning profile."""
    memory.reset_drone(drone_id)
    return {"ok": True, "drone_id": drone_id}


@app.get("/api/v1/system/state")
async def system_state():
    """Return current control and memory state for audit visibility."""
    state = human_control.active_state()
    return {
        "human_control": asdict(state) if state else None,
        "memory_snapshot": memory.snapshot(),
    }
