# ─── Standard library imports ───
import random
from enum import Enum, auto
from dataclasses import dataclass

# ─── Project imports ───
from .config import config
from .infra_agent import NetworkState


class PollSpeed(Enum):
    FAST = auto()
    SLOW = auto()

    def __str__(self) -> str:
        return f"{self.name}_POLL"

@dataclass(frozen=True)
class ScheduleDecision:
    poll_speed: PollSpeed
    base_interval: int
    jitter: float
    sleep_for: float

class SchedulingPolicy:
    """
    Monotonic FSM-driven scheduler.

    Invariant:
    - DOWN / DEGRADED states poll aggressively to accelerate recovery.
    - All other states (UP) poll conservatively to preserve steady-state.
    """

    FAST_STATES = {NetworkState.DOWN, NetworkState.DEGRADED}

    def __init__(self):
        self.base_interval = config.CYCLE_INTERVAL_S
        self.jitter_max = config.POLLING_JITTER_S
        self.scalars = {
            PollSpeed.FAST: config.FAST_POLL_SCALAR,
            PollSpeed.SLOW: config.SLOW_POLL_SCALAR,
        }

    def next_schedule(self, *, elapsed: float, state: NetworkState) -> ScheduleDecision:
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
