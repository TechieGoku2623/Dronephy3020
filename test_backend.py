"""Backend tests for GridOS-Logic v2.0."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.memory_engine import SelfAdaptingMemory
from app.models import MissionFeedback, PowerLineSegment, SafetyStatus
from app.physics_engine import evaluate_segment_physics
from app.routing_engine import haversine_km


def build_settings(**overrides) -> Settings:
    """Build deterministic app settings for tests."""
    base = Settings(
        app_name="GridOS Test",
        app_version="2.1.0-test",
        environment="test",
        cors_origins=["http://localhost:3000"],
        weather_api_base="",
        require_api_key=False,
        api_keys={},
        default_tenant_id="public",
        enforce_tenant_header=False,
        enable_rate_limit=False,
        rate_limit_per_minute=9999,
        api_workers=1,
        api_timeout_seconds=60,
        log_level="WARNING",
    )
    return Settings(**{**base.__dict__, **overrides})


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
    memory = SelfAdaptingMemory()
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
    app = create_app(build_settings())
    client = TestClient(app)
    client.post(
        "/api/v1/weather/override",
        json={
            "quadrant": "NW",
            "wind_speed_ms": 26.0,
            "heavy_precipitation": True,
        },
        headers={"X-Tenant-ID": "acme"},
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
        headers={"X-Tenant-ID": "acme"},
    )
    payload = response.json()
    assert payload["safety_status"] == SafetyStatus.UNSAFE_WEATHER_LOCKOUT.value
    assert payload["target_segment_id"] in {"NO_SAFE_SEGMENT", "OPERATOR_LOCKOUT"}


def test_human_force_segment_override() -> None:
    """Human control can force a specific safe segment."""
    app = create_app(build_settings())
    client = TestClient(app)
    client.post(
        "/api/v1/control/command",
        json={
            "operator_id": "ops-chief",
            "force_segment_id": "SEG-B3",
            "emergency_lockout": False,
            "reason": "Prefer low-risk maintenance corridor",
        },
        headers={"X-Tenant-ID": "acme"},
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
        headers={"X-Tenant-ID": "acme"},
    )
    payload = response.json()
    assert payload["target_segment_id"] == "SEG-B3"
    assert payload["safety_status"] == SafetyStatus.SAFE.value


def test_api_key_required_in_hardened_mode() -> None:
    """Production-style mode should reject unauthenticated access."""
    app = create_app(
        build_settings(
            require_api_key=True,
            api_keys={"ops": "super-secret-token"},
        )
    )
    client = TestClient(app)
    unauthorized = client.get("/api/v1/grid/segments", headers={"X-Tenant-ID": "acme"})
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/api/v1/grid/segments",
        headers={"X-Tenant-ID": "acme", "X-API-Key": "super-secret-token"},
    )
    assert authorized.status_code == 200


def test_tenant_isolation_for_weather_override() -> None:
    """Overrides in one tenant should not leak into another tenant."""
    app = create_app(build_settings())
    client = TestClient(app)
    client.post(
        "/api/v1/weather/override",
        json={"quadrant": "NW", "wind_speed_ms": 40.0, "heavy_precipitation": True},
        headers={"X-Tenant-ID": "tenant-a"},
    )

    a_response = client.post(
        "/api/v1/routing/next-perch",
        json={
            "drone_id": "DRONE-A",
            "latitude": 37.7720,
            "longitude": -122.4410,
            "battery_percentage": 80.0,
            "consumption_rate_per_min": 1.0,
        },
        headers={"X-Tenant-ID": "tenant-a"},
    ).json()
    b_response = client.post(
        "/api/v1/routing/next-perch",
        json={
            "drone_id": "DRONE-B",
            "latitude": 37.7720,
            "longitude": -122.4410,
            "battery_percentage": 80.0,
            "consumption_rate_per_min": 1.0,
        },
        headers={"X-Tenant-ID": "tenant-b"},
    ).json()

    assert a_response["safety_status"] == SafetyStatus.UNSAFE_WEATHER_LOCKOUT.value
    assert b_response["safety_status"] == SafetyStatus.SAFE.value


def test_production_rejects_wildcard_cors() -> None:
    """Production mode must reject wildcard CORS configuration."""
    with pytest.raises(ValueError, match="wildcard CORS"):
        create_app(
            build_settings(
                environment="production",
                cors_origins=["*"],
                require_api_key=True,
                api_keys={"ops": "a" * 30},
            )
        )


def test_production_rejects_short_api_keys() -> None:
    """Production mode must reject weak API keys."""
    with pytest.raises(ValueError, match="too short"):
        create_app(
            build_settings(
                environment="production",
                require_api_key=True,
                api_keys={"ops": "short"},
            )
        )
