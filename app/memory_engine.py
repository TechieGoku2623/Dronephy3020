"""Self-adapting memory for drone routing decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from app.models import MissionFeedback


@dataclass
class SegmentLearningState:
    """Learning state for one segment from one drone perspective."""

    attempts: int = 0
    successes: int = 0
    ema_charge_rate_pct_per_hr: float = 0.0

    def success_ratio(self) -> float:
        """Compute historical success ratio with cold-start neutrality."""
        if self.attempts == 0:
            return 0.5
        return self.successes / self.attempts

    def update(self, feedback: MissionFeedback, smoothing: float = 0.35) -> None:
        """Update statistics using outcome + smoothed charge-rate estimate."""
        self.attempts += 1
        if feedback.successful_perch:
            self.successes += 1

        if self.attempts == 1:
            self.ema_charge_rate_pct_per_hr = feedback.observed_charge_rate_pct_per_hr
            return

        self.ema_charge_rate_pct_per_hr = (
            smoothing * feedback.observed_charge_rate_pct_per_hr
            + (1.0 - smoothing) * self.ema_charge_rate_pct_per_hr
        )


@dataclass
class DroneMemoryProfile:
    """Aggregated memory for one drone."""

    segment_history: dict[str, SegmentLearningState] = field(default_factory=dict)

    def get_or_create(self, segment_id: str) -> SegmentLearningState:
        """Fetch existing segment state or initialize a neutral one."""
        if segment_id not in self.segment_history:
            self.segment_history[segment_id] = SegmentLearningState()
        return self.segment_history[segment_id]


class SelfAdaptingMemory:
    """In-memory learning service with bounded scoring influence."""

    def __init__(self) -> None:
        self._profiles: dict[str, DroneMemoryProfile] = {}
        self._lock = Lock()

    def _profile(self, drone_id: str) -> DroneMemoryProfile:
        if drone_id not in self._profiles:
            self._profiles[drone_id] = DroneMemoryProfile()
        return self._profiles[drone_id]

    def score_multiplier(self, drone_id: str, segment_id: str) -> float:
        """Return bounded multiplier based on historical success and charge yield."""
        with self._lock:
            segment = self._profile(drone_id).get_or_create(segment_id)
            success_component = 0.75 + (segment.success_ratio() * 0.75)
            charge_component = 1.0 + min(segment.ema_charge_rate_pct_per_hr / 200.0, 0.25)
            multiplier = success_component * charge_component
            return max(0.6, min(multiplier, 1.6))

    def register_feedback(self, feedback: MissionFeedback) -> None:
        """Update memory using observed mission feedback."""
        with self._lock:
            profile = self._profile(feedback.drone_id)
            profile.get_or_create(feedback.segment_id).update(feedback)

    def reset_drone(self, drone_id: str) -> None:
        """Reset profile for one drone."""
        with self._lock:
            self._profiles.pop(drone_id, None)

    def snapshot(self) -> dict[str, dict[str, dict[str, float]]]:
        """Expose summary for dashboards or operator audit trails."""
        with self._lock:
            view: dict[str, dict[str, dict[str, float]]] = {}
            for drone_id, profile in self._profiles.items():
                view[drone_id] = {}
                for segment_id, state in profile.segment_history.items():
                    view[drone_id][segment_id] = {
                        "attempts": float(state.attempts),
                        "success_ratio": state.success_ratio(),
                        "ema_charge_rate_pct_per_hr": state.ema_charge_rate_pct_per_hr,
                    }
            return view
