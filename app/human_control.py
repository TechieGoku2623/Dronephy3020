"""Human command-and-control authority over autonomous decisions."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import time

from app.models import HumanControlCommand


@dataclass
class HumanControlState:
    """Current operator authority state."""

    operator_id: str
    emergency_lockout: bool
    force_segment_id: str | None
    reason: str
    updated_at_epoch_s: float


class HumanControlLayer:
    """Applies mandatory human authority to autonomous route decisions."""

    def __init__(self) -> None:
        self._state: HumanControlState | None = None
        self._lock = Lock()

    def update(self, command: HumanControlCommand) -> HumanControlState:
        """Set the active human command."""
        with self._lock:
            self._state = HumanControlState(
                operator_id=command.operator_id,
                emergency_lockout=command.emergency_lockout,
                force_segment_id=command.force_segment_id,
                reason=command.reason,
                updated_at_epoch_s=time(),
            )
            return self._state

    def clear(self) -> None:
        """Clear any human override and return to autonomous mode."""
        with self._lock:
            self._state = None

    def active_state(self) -> HumanControlState | None:
        """Get current human authority state."""
        with self._lock:
            return self._state

    def enforce(
        self,
        candidate_segments: list[str],
    ) -> tuple[str | None, str | None]:
        """
        Apply operator control to candidate segments.

        Returns:
            (forced_segment_id, lockout_reason)
        """
        with self._lock:
            if self._state is None:
                return None, None

            if self._state.emergency_lockout:
                return None, f"Grounded by operator {self._state.operator_id}: {self._state.reason}"

            if self._state.force_segment_id and self._state.force_segment_id in candidate_segments:
                return self._state.force_segment_id, None

            if self._state.force_segment_id and self._state.force_segment_id not in candidate_segments:
                return None, (
                    f"Operator requested {self._state.force_segment_id} but it is not a safe candidate; "
                    "autonomous selection retained."
                )

            return None, None
