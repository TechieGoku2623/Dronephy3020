"""Thermal + electromagnetic models for line-perching decisions."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi

from app.models import PowerLineSegment, SafetyStatus

MU_0 = 4 * pi * 1e-7  # Vacuum permeability (T*m/A)
DEFAULT_CLAMP_DISTANCE_M = 0.05
LOW_INDUCTION_THRESHOLD_MICROTESLA = 15.0
THERMAL_LIMIT_C = 90.0
CORONA_THD_THRESHOLD = 15.0


@dataclass
class PhysicsAssessment:
    """Physics outputs used by routing + dashboard rendering."""

    conductor_temp_c: float
    magnetic_field_microtesla: float
    optimal_clamp_angle_degrees: float
    safety_status: SafetyStatus


def ieee_738_conductor_temperature(segment: PowerLineSegment) -> float:
    """
    Estimate conductor temperature from Joule heating vs wind convection.

    This uses a compact approximation of IEEE-738 behavior:
    - heating ~ I^2 * R(T)
    - cooling ~ h(v) * delta_t
    """
    base_resistance_ohm_per_m = 9.8e-5
    resistance_temp_coeff = 0.0039
    resistance = base_resistance_ohm_per_m * (
        1 + resistance_temp_coeff * (segment.ambient_temp_c - 20.0)
    )
    joule_heating_w_per_m = (segment.current_amperage**2) * resistance

    # Wind speed dominates convective cooling; constant term avoids singularity.
    convection_gain = 8.0 + (2.7 * segment.wind_speed_ms)
    temp_rise = joule_heating_w_per_m / convection_gain
    return segment.ambient_temp_c + temp_rise


def biot_savart_field_microtesla(
    current_amperage: float,
    clamp_distance_m: float = DEFAULT_CLAMP_DISTANCE_M,
) -> float:
    """Compute magnetic flux density near a straight current-carrying conductor."""
    tesla = (MU_0 * current_amperage) / (2 * pi * clamp_distance_m)
    return tesla * 1e6


def harmonic_optimized_clamp_angle(total_harmonic_distortion: float) -> float:
    """
    Shift perpendicular clamp angle (90 deg) away from harmonic dead zones.

    Positive THD nudges angle away from pure perpendicular. The output is
    bounded to a practical contact window.
    """
    thd_shift = max(-18.0, min(total_harmonic_distortion * 0.9, 18.0))
    return max(60.0, min(90.0 + thd_shift, 120.0))


def evaluate_segment_physics(segment: PowerLineSegment) -> PhysicsAssessment:
    """Run thermal, induction, and harmonic safety gates for one segment."""
    conductor_temp = ieee_738_conductor_temperature(segment)
    magnetic_field = biot_savart_field_microtesla(segment.current_amperage)
    optimal_angle = harmonic_optimized_clamp_angle(segment.total_harmonic_distortion)

    safety = SafetyStatus.SAFE
    if conductor_temp > THERMAL_LIMIT_C:
        safety = SafetyStatus.UNSAFE_OVERHEATING
    elif segment.total_harmonic_distortion > CORONA_THD_THRESHOLD:
        safety = SafetyStatus.UNSAFE_CORONA_RISK
    elif magnetic_field < LOW_INDUCTION_THRESHOLD_MICROTESLA:
        safety = SafetyStatus.UNSAFE_LOW_INDUCTION

    return PhysicsAssessment(
        conductor_temp_c=conductor_temp,
        magnetic_field_microtesla=magnetic_field,
        optimal_clamp_angle_degrees=optimal_angle,
        safety_status=safety,
    )
