# ─── Standard library imports ───
import random

# ─── Project imports ───
from .config import config
from .logger import get_logger
from .infra_agent import NetworkState


class SchedulingPolicy:
    def __init__(self):
        self.base_interval = config.CYCLE_INTERVAL_S
        self.polling_jitter = config.POLLING_JITTER_S
        self.fast_scalar = config.FAST_POLL_SCALAR
        self.slow_scalar = config.SLOW_POLL_SCALAR
        self.min_ttl = config.CLOUDFLARE_MIN_TTL_S
        self.logger = get_logger("scheduling_policy")

    def interval_for_state(self, state: NetworkState) -> int:
        """
        Returns the minimum interval (seconds) for the given network state.
        This value is guaranteed to be a lower bound on scheduling.
        """

        scalar = self._scalar_for_state(state)
        minimum_interval = int(self.base_interval * scalar)
        return minimum_interval

    def _scalar_for_state(self, state: NetworkState) -> float:
        if state in (NetworkState.DOWN, NetworkState.DEGRADED):
            return self.fast_scalar
        return self.slow_scalar 

    def next_sleep(self, *, elapsed: float, state: NetworkState) -> float:
        """
        Computes the next sleep duration, enforcing:
        - a minimum interval per state
        - positive-only jitter to avoid detectable periodicity
        """
        minimum_interval = self.interval_for_state(state)
        jitter = random.uniform(0, self.polling_jitter)
        scheduled_interval = minimum_interval + jitter
        return max(0.0, scheduled_interval - elapsed)
