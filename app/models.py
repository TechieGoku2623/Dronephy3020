"""Pydantic models for GridOS-Logic routing and controls."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SafetyStatus(str, Enum):
    """Safety decision emitted by the routing and physics engines."""

    SAFE = "SAFE"
    UNSAFE_OVERHEATING = "UNSAFE_OVERHEATING"
    UNSAFE_LOW_INDUCTION = "UNSAFE_LOW_INDUCTION"
    UNSAFE_CORONA_RISK = "UNSAFE_CORONA_RISK"
    UNSAFE_WEATHER_LOCKOUT = "UNSAFE_WEATHER_LOCKOUT"


class DroneTelemetry(BaseModel):
    """Live drone position and battery consumption data."""

    model_config = ConfigDict(extra="forbid", strict=True)

    drone_id: str = Field(min_length=3, max_length=64)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    battery_percentage: float = Field(ge=0.0, le=100.0)
    consumption_rate_per_min: float = Field(gt=0.0, le=20.0)


class PowerLineSegment(BaseModel):
    """Electrical and geo-spatial properties of a line segment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    segment_id: str = Field(min_length=2, max_length=64)
    lat_start: float = Field(ge=-90.0, le=90.0)
    lon_start: float = Field(ge=-180.0, le=180.0)
    lat_end: float = Field(ge=-90.0, le=90.0)
    lon_end: float = Field(ge=-180.0, le=180.0)
    current_amperage: float = Field(gt=0.0, le=5000.0)
    ambient_temp_c: float = Field(ge=-50.0, le=120.0)
    wind_speed_ms: float = Field(ge=0.0, le=80.0)
    total_harmonic_distortion: float = Field(ge=0.0, le=100.0)


class RouteRecommendation(BaseModel):
    """Recommended segment to perch for charging and safety status."""

    model_config = ConfigDict(extra="forbid", strict=True)

    target_segment_id: str = Field(min_length=2, max_length=64)
    target_coordinates: tuple[float, float]
    estimated_charge_rate_pct_per_hr: float = Field(ge=0.0)
    safety_status: SafetyStatus
    optimal_clamp_angle_degrees: float = Field(ge=0.0, le=180.0)
    rationale: str = Field(min_length=8, max_length=512)

    @field_validator("target_coordinates")
    @classmethod
    def _validate_coordinate_pair(cls, value: tuple[float, float]) -> tuple[float, float]:
        lat, lon = value
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise ValueError("target_coordinates must be [lat, lon] bounds")
        return value


class WeatherOverrideInput(BaseModel):
    """Operator input that simulates weather in a specific quadrant."""

    model_config = ConfigDict(extra="forbid", strict=True)

    quadrant: str = Field(min_length=2, max_length=32)
    wind_speed_ms: float = Field(ge=0.0, le=80.0)
    heavy_precipitation: bool


class HumanControlCommand(BaseModel):
    """Human authority command to enforce lock or force a segment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    operator_id: str = Field(min_length=3, max_length=64)
    force_segment_id: str | None = Field(default=None, min_length=2, max_length=64)
    emergency_lockout: bool = False
    reason: str = Field(min_length=4, max_length=256)


class MissionFeedback(BaseModel):
    """Feedback loop payload used by self-adapting memory."""

    model_config = ConfigDict(extra="forbid", strict=True)

    drone_id: str = Field(min_length=3, max_length=64)
    segment_id: str = Field(min_length=2, max_length=64)
    successful_perch: bool
    observed_charge_rate_pct_per_hr: float = Field(ge=0.0, le=100.0)


class SegmentState(BaseModel):
    """Public segment state used by the frontend dashboard."""

    model_config = ConfigDict(extra="forbid", strict=True)

    segment: PowerLineSegment
    safety_status: SafetyStatus
    magnetic_field_microtesla: float
    conductor_temp_c: float
