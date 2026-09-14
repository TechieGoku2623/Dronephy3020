"""Predictive maintenance and anomaly scoring for drones and line segments."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import time

from app.models import (
    AnomalySeverity,
    DroneTelemetry,
    MaintenanceAlert,
    MaintenanceReport,
    MissionFeedback,
    PowerLineSegment,
)

THERMAL_WATCH_C = 75.0
THERMAL_CRITICAL_C = 88.0
THD_WATCH = 10.0
THD_CRITICAL = 14.0
LOW_CHARGE_WATCH = 8.0
FAILURE_WATCH_RATIO = 0.35
FAILURE_CRITICAL_RATIO = 0.6
CONSUMPTION_WATCH = 3.5
CONSUMPTION_CRITICAL = 6.0


@dataclass
class TelemetrySample:
    """One telemetry observation used for drain-rate anomaly detection."""

    epoch_s: float
    battery_percentage: float
    consumption_rate_per_min: float


@dataclass
class SegmentHealth:
    """Rolling health state for one power-line segment."""

    attempts: int = 0
    failures: int = 0
    ema_charge_rate_pct_per_hr: float = 0.0
    last_conductor_temp_c: float = 0.0
    last_thd: float = 0.0
    last_field_ut: float = 0.0
    thermal_stress_hits: int = 0
    harmonic_stress_hits: int = 0

    def failure_ratio(self) -> float:
        """Return perch-failure ratio with a cold-start of zero."""
        if self.attempts == 0:
            return 0.0
        return self.failures / self.attempts


@dataclass
class DroneHealth:
    """Rolling health state for one drone."""

    samples: deque[TelemetrySample] = field(default_factory=lambda: deque(maxlen=12))
    last_consumption_rate: float = 0.0
    last_battery_percentage: float = 100.0


class PredictiveMaintenanceEngine:
    """Scores emerging failures so routing can avoid degrading assets."""

    def __init__(self) -> None:
        self._drones: dict[str, DroneHealth] = {}
        self._segments: dict[str, SegmentHealth] = {}
        self._lock = Lock()

    def reset(self) -> None:
        """Clear all learned maintenance state."""
        with self._lock:
            self._drones.clear()
            self._segments.clear()

    def reset_drone(self, drone_id: str) -> None:
        """Clear one drone's telemetry history."""
        with self._lock:
            self._drones.pop(drone_id, None)

    def _segment(self, segment_id: str) -> SegmentHealth:
        if segment_id not in self._segments:
            self._segments[segment_id] = SegmentHealth()
        return self._segments[segment_id]

    def ingest_telemetry(self, telemetry: DroneTelemetry) -> None:
        """Record live drone telemetry for drain-rate anomaly scoring."""
        with self._lock:
            health = self._drones.setdefault(telemetry.drone_id, DroneHealth())
            health.last_consumption_rate = telemetry.consumption_rate_per_min
            health.last_battery_percentage = telemetry.battery_percentage
            health.samples.append(
                TelemetrySample(
                    epoch_s=time(),
                    battery_percentage=telemetry.battery_percentage,
                    consumption_rate_per_min=telemetry.consumption_rate_per_min,
                )
            )

    def observe_segment(
        self,
        segment: PowerLineSegment,
        conductor_temp_c: float,
        magnetic_field_microtesla: float,
    ) -> None:
        """Update segment wear signals from the latest physics snapshot."""
        with self._lock:
            health = self._segment(segment.segment_id)
            health.last_conductor_temp_c = conductor_temp_c
            health.last_thd = segment.total_harmonic_distortion
            health.last_field_ut = magnetic_field_microtesla
            if conductor_temp_c >= THERMAL_WATCH_C:
                health.thermal_stress_hits += 1
            if segment.total_harmonic_distortion >= THD_WATCH:
                health.harmonic_stress_hits += 1

    def register_feedback(self, feedback: MissionFeedback) -> None:
        """Fold perch outcomes into segment remaining-useful-life estimates."""
        with self._lock:
            health = self._segment(feedback.segment_id)
            health.attempts += 1
            if not feedback.successful_perch:
                health.failures += 1
            if health.attempts == 1:
                health.ema_charge_rate_pct_per_hr = feedback.observed_charge_rate_pct_per_hr
                return
            health.ema_charge_rate_pct_per_hr = (
                0.4 * feedback.observed_charge_rate_pct_per_hr
                + 0.6 * health.ema_charge_rate_pct_per_hr
            )

    def routing_multiplier(self, segment_id: str) -> float:
        """Return a bounded score penalty for degrading segments."""
        severity, score = self._segment_score(segment_id)
        if severity == AnomalySeverity.CRITICAL:
            return 0.45
        if severity == AnomalySeverity.WATCH:
            return 0.75
        return 1.0 - min(score / 400.0, 0.08)

    def should_skip_autonomous(self, segment_id: str) -> bool:
        """True when a segment is too degraded for autonomous perch selection."""
        severity, _ = self._segment_score(segment_id)
        return severity == AnomalySeverity.CRITICAL

    def segment_alert(self, segment_id: str) -> MaintenanceAlert:
        """Build the public alert for one segment."""
        severity, score = self._segment_score(segment_id)
        issue, action = self._segment_guidance(segment_id, severity)
        return MaintenanceAlert(
            entity_type="segment",
            entity_id=segment_id,
            severity=severity,
            anomaly_score=round(score, 2),
            predicted_issue=issue,
            recommended_action=action,
            confidence=min(0.95, 0.35 + score / 140.0),
        )

    def drone_alert(self, drone_id: str) -> MaintenanceAlert:
        """Build the public alert for one drone."""
        severity, score = self._drone_score(drone_id)
        if severity == AnomalySeverity.CRITICAL:
            issue = "Battery drain is accelerating beyond the declared consumption model."
            action = "Ground the airframe for pack inspection before the next perch cycle."
        elif severity == AnomalySeverity.WATCH:
            issue = "Consumption trend is elevated; remaining useful flight time may shrink."
            action = "Schedule a mid-shift battery health check and reduce sortie length."
        else:
            issue = "No predictive battery or airframe anomaly is currently indicated."
            action = "Continue autonomous routing with standard preflight checks."
        return MaintenanceAlert(
            entity_type="drone",
            entity_id=drone_id,
            severity=severity,
            anomaly_score=round(score, 2),
            predicted_issue=issue,
            recommended_action=action,
            confidence=min(0.92, 0.3 + score / 150.0),
        )

    def report(self) -> MaintenanceReport:
        """Return fleet-wide alerts sorted by severity then score."""
        with self._lock:
            drone_ids = list(self._drones)
            segment_ids = list(self._segments)

        alerts = [self.drone_alert(drone_id) for drone_id in drone_ids]
        alerts.extend(self.segment_alert(segment_id) for segment_id in segment_ids)
        alerts.sort(key=lambda alert: (alert.severity != AnomalySeverity.CRITICAL, -alert.anomaly_score))

        if any(alert.severity == AnomalySeverity.CRITICAL for alert in alerts):
            highest = AnomalySeverity.CRITICAL
            summary = "Critical predictive-maintenance findings require operator review before the next sortie."
        elif any(alert.severity == AnomalySeverity.WATCH for alert in alerts):
            highest = AnomalySeverity.WATCH
            summary = "Watch-level wear or drain signals are present; continue with heightened inspection cadence."
        else:
            highest = AnomalySeverity.NORMAL
            summary = "No predictive-maintenance anomalies exceed the watch threshold."

        return MaintenanceReport(alerts=alerts, highest_severity=highest, summary=summary)

    def _segment_score(self, segment_id: str) -> tuple[AnomalySeverity, float]:
        with self._lock:
            health = self._segments.get(segment_id, SegmentHealth())
            failure_ratio = health.failure_ratio()
            temp = health.last_conductor_temp_c
            thd = health.last_thd
            charge = health.ema_charge_rate_pct_per_hr
            thermal_hits = health.thermal_stress_hits
            harmonic_hits = health.harmonic_stress_hits
            attempts = health.attempts

        score = 0.0
        score += min(failure_ratio * 100.0, 50.0)
        if temp >= THERMAL_WATCH_C:
            score += min((temp - THERMAL_WATCH_C) * 3.2, 25.0)
        if thd >= THD_WATCH:
            score += min((thd - THD_WATCH) * 6.0, 20.0)
        if attempts >= 2 and charge < LOW_CHARGE_WATCH:
            score += 15.0
        score += min(thermal_hits * 2.0, 10.0)
        score += min(harmonic_hits * 1.5, 8.0)
        score = max(0.0, min(score, 100.0))

        if (
            failure_ratio >= FAILURE_CRITICAL_RATIO
            or temp >= THERMAL_CRITICAL_C
            or thd >= THD_CRITICAL
        ):
            return AnomalySeverity.CRITICAL, score
        if (
            failure_ratio >= FAILURE_WATCH_RATIO
            or temp >= THERMAL_WATCH_C
            or thd >= THD_WATCH
            or (attempts >= 2 and charge < LOW_CHARGE_WATCH)
        ):
            return AnomalySeverity.WATCH, score
        return AnomalySeverity.NORMAL, score

    def _drone_score(self, drone_id: str) -> tuple[AnomalySeverity, float]:
        with self._lock:
            health = self._drones.get(drone_id)
            if health is None or not health.samples:
                return AnomalySeverity.NORMAL, 0.0
            samples = list(health.samples)
            declared = health.last_consumption_rate

        score = 0.0
        if declared >= CONSUMPTION_WATCH:
            score += min((declared - CONSUMPTION_WATCH) * 12.0, 30.0)

        if len(samples) >= 2:
            first, last = samples[0], samples[-1]
            elapsed_min = max((last.epoch_s - first.epoch_s) / 60.0, 1e-3)
            observed_drain = max(0.0, first.battery_percentage - last.battery_percentage) / elapsed_min
            expected = max(declared, 0.1)
            if observed_drain > expected * 1.35:
                score += min((observed_drain / expected - 1.35) * 40.0, 40.0)

        score = max(0.0, min(score, 100.0))
        if declared >= CONSUMPTION_CRITICAL or score >= 70.0:
            return AnomalySeverity.CRITICAL, score
        if declared >= CONSUMPTION_WATCH or score >= 25.0:
            return AnomalySeverity.WATCH, score
        return AnomalySeverity.NORMAL, score

    def _segment_guidance(self, segment_id: str, severity: AnomalySeverity) -> tuple[str, str]:
        with self._lock:
            health = self._segments.get(segment_id, SegmentHealth())
            failure_ratio = health.failure_ratio()
            temp = health.last_conductor_temp_c
            thd = health.last_thd

        if severity == AnomalySeverity.CRITICAL:
            if failure_ratio >= FAILURE_CRITICAL_RATIO:
                return (
                    "Repeated perch failures indicate clamp or hardware wear on this span.",
                    "Remove the segment from autonomous routing and dispatch a line crew.",
                )
            if temp >= THERMAL_CRITICAL_C:
                return (
                    "Conductor temperature is approaching the IEEE-738 thermal limit.",
                    "Hold perch operations and request a thermal inspection of the span.",
                )
            return (
                "Harmonic distortion is near the corona threshold and will degrade clamp life.",
                "Defer perching until a harmonics survey confirms a safer clamp window.",
            )
        if severity == AnomalySeverity.WATCH:
            if thd >= THD_WATCH:
                return (
                    "Rising harmonics will shorten clamp contact life on this segment.",
                    "Increase inspection cadence and prefer alternate spans when available.",
                )
            if temp >= THERMAL_WATCH_C:
                return (
                    "Thermal wear is accumulating on this conductor under current load.",
                    "Limit dwell time and re-check conductor temperature before the next perch.",
                )
            return (
                "Charge yield or perch reliability is trending below the healthy band.",
                "Keep the segment eligible but weight it down until more successes arrive.",
            )
        return (
            "Segment wear indicators are within the normal operating band.",
            "Keep the span in the autonomous candidate set.",
        )
