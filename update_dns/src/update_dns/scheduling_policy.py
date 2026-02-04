# ─── Standard library imports ───
import random
from enum import Enum, auto
from dataclasses import dataclass

# ─── Project imports ───
from .config import config
from .readiness import ReadinessState


class PollSpeed(Enum):
    """
    High-level polling modes.

    • FAST — aggressive polling during recovery or uncertainty
    • SLOW — steady-state polling once things are stable
    """
    FAST = auto()
    SLOW = auto()

    def __str__(self) -> str:
        return f"{self.name}_POLL"

@dataclass(frozen=True)
class ScheduleDecision:
    """
    Concrete scheduling outcome for a single control-loop iteration.

    All values are precomputed so callers can sleep without
    re-deriving timing logic.
    """
    poll_speed: PollSpeed
    base_interval: int
    jitter: float
    sleep_for: float

class SchedulingPolicy:
    """
    Readiness-aware polling policy.

    • Poll faster when the system is unhealthy or uncertain
    • Poll slower once steady-state is reached
    • Add jitter to avoid sync patterns and API abuse

    This class is stateless aside from configuration and is safe
    to call once per control-loop cycle.
    """
    FAST_STATES = {ReadinessState.NOT_READY, ReadinessState.PROBING}

    def __init__(self):
        self.base_interval = config.CYCLE_INTERVAL_S
        self.jitter_max = config.POLLING_JITTER_S
        self.scalars = {
            PollSpeed.FAST: config.FAST_POLL_SCALAR,
            PollSpeed.SLOW: config.SLOW_POLL_SCALAR,
        }

    def next_schedule(
            self, 
            *, 
            elapsed: float, 
            state: ReadinessState
        ) -> ScheduleDecision:
        """
        Compute the next polling interval for the control loop.

        • Select FAST or SLOW polling based on readiness
        • Scale the base interval accordingly
        • Apply bounded jitter
        • Account for time already spent in the cycle
        """
        poll_speed = (
            PollSpeed.FAST if state in self.FAST_STATES else PollSpeed.SLOW
        )

        base_interval = int(self.base_interval * self.scalars[poll_speed])
        jitter = random.uniform(0.0, self.jitter_max)
        sleep_for = max(0.0, base_interval + jitter - elapsed)

        return ScheduleDecision(
            poll_speed=poll_speed,
            base_interval=base_interval,
            jitter=jitter,
            sleep_for=sleep_for,
        )
