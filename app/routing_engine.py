"""Geospatial routing core for next-perch recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.human_control import HumanControlLayer
from app.maintenance_engine import PredictiveMaintenanceEngine
from app.memory_engine import SelfAdaptingMemory
from app.models import (
    DroneTelemetry,
    PowerLineSegment,
    RouteRecommendation,
    SafetyStatus,
    SegmentState,
)
from app.physics_engine import evaluate_segment_physics
from app.weather_service import WeatherService

DRONE_CRUISE_SPEED_KMPH = 45.0
BATTERY_SAFETY_FACTOR = 0.70


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate real-world distance in kilometers between two coordinates."""
    earth_radius_km = 6371.0
    lat1_r, lon1_r = radians(lat1), radians(lon1)
    lat2_r, lon2_r = radians(lat2), radians(lon2)
    d_lat = lat2_r - lat1_r
    d_lon = lon2_r - lon1_r
    arc = sin(d_lat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(arc))


def segment_center(segment: PowerLineSegment) -> tuple[float, float]:
    """Compute center point of a power line segment."""
    return ((segment.lat_start + segment.lat_end) / 2, (segment.lon_start + segment.lon_end) / 2)


@dataclass
class _Candidate:
    segment: PowerLineSegment
    score: float
    distance_km: float
    magnetic_field_microtesla: float
    optimal_angle_degrees: float
    estimated_charge_rate: float
    rationale: str


class RoutingEngine:
    """Coordinates safety filters and ranking for next perch selection."""

    def __init__(
        self,
        segments: list[PowerLineSegment],
        weather_service: WeatherService,
        memory: SelfAdaptingMemory,
        human_control: HumanControlLayer,
        maintenance: PredictiveMaintenanceEngine,
    ) -> None:
        self._segments = segments
        self._weather = weather_service
        self._memory = memory
        self._human_control = human_control
        self._maintenance = maintenance

    def max_safe_range_km(self, telemetry: DroneTelemetry) -> float:
        """Estimate safe travel range from battery and consumption rates."""
        minutes_left = telemetry.battery_percentage / telemetry.consumption_rate_per_min
        nominal_range = DRONE_CRUISE_SPEED_KMPH * (minutes_left / 60.0)
        return nominal_range * BATTERY_SAFETY_FACTOR

    async def segment_states(self) -> list[SegmentState]:
        """Return segment safety state snapshot for frontend rendering."""
        states: list[SegmentState] = []
        for segment in self._segments:
            center_lat, center_lon = segment_center(segment)
            weather = await self._weather.assess(center_lat, center_lon, segment.wind_speed_ms)
            physics = evaluate_segment_physics(segment)
            self._maintenance.observe_segment(
                segment,
                physics.conductor_temp_c,
                physics.magnetic_field_microtesla,
            )
            safety = weather.safety_status if weather.safety_status != SafetyStatus.SAFE else physics.safety_status
            alert = self._maintenance.segment_alert(segment.segment_id)
            states.append(
                SegmentState(
                    segment=segment,
                    safety_status=safety,
                    magnetic_field_microtesla=physics.magnetic_field_microtesla,
                    conductor_temp_c=physics.conductor_temp_c,
                    anomaly_score=alert.anomaly_score,
                    anomaly_severity=alert.severity,
                )
            )
        return states

    async def recommend_next_perch(self, telemetry: DroneTelemetry) -> RouteRecommendation:
        """Compute the top routing recommendation using safety-first ranking."""
        safe_range_km = self.max_safe_range_km(telemetry)
        candidates: list[_Candidate] = []
        skip_reasons: list[str] = []

        for segment in self._segments:
            center_lat, center_lon = segment_center(segment)
            distance = haversine_km(telemetry.latitude, telemetry.longitude, center_lat, center_lon)
            if distance > safe_range_km:
                skip_reasons.append(f"{segment.segment_id}: out-of-range({distance:.2f}km)")
                continue

            weather = await self._weather.assess(center_lat, center_lon, segment.wind_speed_ms)
            if weather.safety_status == SafetyStatus.UNSAFE_WEATHER_LOCKOUT:
                skip_reasons.append(f"{segment.segment_id}: weather-lockout")
                continue

            physics = evaluate_segment_physics(segment)
            self._maintenance.observe_segment(
                segment,
                physics.conductor_temp_c,
                physics.magnetic_field_microtesla,
            )
            if physics.safety_status != SafetyStatus.SAFE:
                skip_reasons.append(f"{segment.segment_id}: {physics.safety_status.value}")
                continue

            memory_multiplier = self._memory.score_multiplier(telemetry.drone_id, segment.segment_id)
            maintenance_multiplier = self._maintenance.routing_multiplier(segment.segment_id)
            score = (
                (physics.magnetic_field_microtesla / (distance + 0.1))
                * memory_multiplier
                * maintenance_multiplier
            )
            angle_penalty = 1.0 - abs(physics.optimal_clamp_angle_degrees - 90.0) / 100.0
            estimated_charge_rate = max(0.0, physics.magnetic_field_microtesla * 0.16 * angle_penalty)

            candidates.append(
                _Candidate(
                    segment=segment,
                    score=score,
                    distance_km=distance,
                    magnetic_field_microtesla=physics.magnetic_field_microtesla,
                    optimal_angle_degrees=physics.optimal_clamp_angle_degrees,
                    estimated_charge_rate=min(estimated_charge_rate, 55.0),
                    rationale=(
                        f"score={score:.2f}, distance={distance:.2f}km, "
                        f"field={physics.magnetic_field_microtesla:.2f}uT, "
                        f"memory={memory_multiplier:.2f}, maintenance={maintenance_multiplier:.2f}"
                    ),
                )
            )

        healthy_candidates = [
            candidate
            for candidate in candidates
            if not self._maintenance.should_skip_autonomous(candidate.segment.segment_id)
        ]
        if healthy_candidates:
            skipped_critical = len(candidates) - len(healthy_candidates)
            candidates = healthy_candidates
            if skipped_critical:
                skip_reasons.append(f"{skipped_critical} segment(s) deferred for predictive maintenance")

        if not candidates:
            return RouteRecommendation(
                target_segment_id="NO_SAFE_SEGMENT",
                target_coordinates=(telemetry.latitude, telemetry.longitude),
                estimated_charge_rate_pct_per_hr=0.0,
                safety_status=SafetyStatus.UNSAFE_WEATHER_LOCKOUT,
                optimal_clamp_angle_degrees=90.0,
                rationale="No safe segment available after filters: " + ", ".join(skip_reasons[:5]),
            )

        candidates.sort(key=lambda c: c.score, reverse=True)
        forced_segment_id, human_message = self._human_control.enforce(
            [candidate.segment.segment_id for candidate in candidates]
        )

        if human_message and forced_segment_id is None:
            # Message may indicate lockout or an unavailable force-target.
            if "Grounded by operator" in human_message:
                return RouteRecommendation(
                    target_segment_id="OPERATOR_LOCKOUT",
                    target_coordinates=(telemetry.latitude, telemetry.longitude),
                    estimated_charge_rate_pct_per_hr=0.0,
                    safety_status=SafetyStatus.UNSAFE_WEATHER_LOCKOUT,
                    optimal_clamp_angle_degrees=90.0,
                    rationale=human_message,
                )

        selected = candidates[0]
        if forced_segment_id:
            selected = next(c for c in candidates if c.segment.segment_id == forced_segment_id)

        center = segment_center(selected.segment)
        rationale = selected.rationale
        if forced_segment_id:
            rationale = f"Human override selected segment {forced_segment_id}. {rationale}"
        elif human_message:
            rationale = f"{human_message} {rationale}"

        return RouteRecommendation(
            target_segment_id=selected.segment.segment_id,
            target_coordinates=center,
            estimated_charge_rate_pct_per_hr=selected.estimated_charge_rate,
            safety_status=SafetyStatus.SAFE,
            optimal_clamp_angle_degrees=selected.optimal_angle_degrees,
            rationale=rationale,
        )
