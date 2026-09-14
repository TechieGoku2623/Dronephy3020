"""Backend tests for GridOS-Logic v2.0."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, human_control, memory, weather_service
from app.models import MissionFeedback, PowerLineSegment, SafetyStatus
from app.physics_engine import evaluate_segment_physics
from app.routing_engine import haversine_km


@pytest.fixture(autouse=True)
def reset_global_state() -> None:
    """Reset mutable singleton state between tests."""
    human_control.clear()
    for quadrant in ("NW", "NE", "SW", "SE"):
        weather_service.clear_override(quadrant)
    memory.reset_drone("DRONE-TEST")
    memory.reset_drone("DRONE-LOCKOUT")


def test_haversine_distance_basics() -> None:
    """Geospatial metric sanity checks."""
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0, abs=1e-6)
    sf_to_oakland = haversine_km(37.7749, -122.4194, 37.8044, -122.2711)
    assert sf_to_oakland == pytest.approx(13.4, rel=0.06)


def test_harmonic_edge_case_triggers_corona_status() -> None:
    """THD beyond limit should force corona-risk safety status."""
    segment = PowerLineSegment(
        segment_id="EDGE-THD",
        lat_start=37.1,
        lon_start=-122.1,
        lat_end=37.2,
        lon_end=-122.2,
        current_amperage=850.0,
        ambient_temp_c=22.0,
        wind_speed_ms=4.0,
        total_harmonic_distortion=21.0,
    )
    result = evaluate_segment_physics(segment)
    assert result.safety_status == SafetyStatus.UNSAFE_CORONA_RISK
    assert result.optimal_clamp_angle_degrees > 90.0


def test_memory_multiplier_increases_after_success_feedback() -> None:
    """Self-adapting memory should reward consistent successful segments."""
    baseline = memory.score_multiplier("DRONE-TEST", "SEG-B3")
    for _ in range(4):
        memory.register_feedback(
            MissionFeedback(
                drone_id="DRONE-TEST",
                segment_id="SEG-B3",
                successful_perch=True,
                observed_charge_rate_pct_per_hr=35.0,
            )
        )
    improved = memory.score_multiplier("DRONE-TEST", "SEG-B3")
    assert improved > baseline


def test_weather_override_forces_lockout() -> None:
    """A severe weather override should ground recommendations."""
    client = TestClient(app)
    client.post(
        "/api/v1/weather/override",
        json={
            "quadrant": "NW",
            "wind_speed_ms": 26.0,
            "heavy_precipitation": True,
        },
    )
    response = client.post(
        "/api/v1/routing/next-perch",
        json={
            "drone_id": "DRONE-LOCKOUT",
            "latitude": 37.7722,
            "longitude": -122.4411,
            "battery_percentage": 78.0,
            "consumption_rate_per_min": 1.2,
        },
    )
    payload = response.json()
    assert payload["safety_status"] == SafetyStatus.UNSAFE_WEATHER_LOCKOUT.value
    assert payload["target_segment_id"] in {"NO_SAFE_SEGMENT", "OPERATOR_LOCKOUT"}


def test_human_force_segment_override() -> None:
    """Human control can force a specific safe segment."""
    client = TestClient(app)
    client.post(
        "/api/v1/control/command",
        json={
            "operator_id": "ops-chief",
            "force_segment_id": "SEG-B3",
            "emergency_lockout": False,
            "reason": "Prefer low-risk maintenance corridor",
        },
    )
    response = client.post(
        "/api/v1/routing/next-perch",
        json={
            "drone_id": "DRONE-TEST",
            "latitude": 37.7712,
            "longitude": -122.4444,
            "battery_percentage": 70.0,
            "consumption_rate_per_min": 1.0,
        },
    )
    payload = response.json()
    assert payload["target_segment_id"] == "SEG-B3"
    assert payload["safety_status"] == SafetyStatus.SAFE.value
