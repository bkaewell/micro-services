# --- Standard library imports ---
import random

# --- Project imports ---
from .config import Config
from .logger import get_logger
from .infra_agent import NetworkState


DNS_UPDATE_JITTER = 5  # seconds (internal safety margin)

# config.py
CYCLE_INTERVAL = 60          # baseline (steady state)
FAST_POLL_SCALAR = 0.5       # 4x faster when unstable
#SLOW_POLL_SCALAR = 2.0       # steady-state
SLOW_POLL_SCALAR = 1.0       # steady-state

class SchedulingPolicy:
    def __init__(self):
        self.base_interval = Config.CYCLE_INTERVAL
        self.min_ttl = Config.CLOUDFLARE_MIN_TTL
        self.enforce_policy = Config.ENFORCE_TTL_POLICY
        self.jitter = DNS_UPDATE_JITTER

        #self.fast_scalar = Config.FAST_POLL_SCALAR
        #self.slow_scalar = Config.SLOW_POLL_SCALAR

        self.fast_scalar = FAST_POLL_SCALAR
        self.slow_scalar = SLOW_POLL_SCALAR       

        self.logger = get_logger("scheduling_policy")

    def interval_for_state(self, state: NetworkState) -> int:
        """
        Returns the effective interval (seconds) for the given network state.
        """

        scalar = self._scalar_for_state(state)
        requested = int(self.base_interval * scalar)

        min_safe = self.min_ttl + self.jitter

        # if self.enforce_policy and requested < min_safe:
        #     self.logger.debug(
        #         "Interval %ss below safe minimum (%ss). Enforcing.",
        #         requested,
        #         min_safe,
        #     )
        #     return min_safe

        return requested

    def _scalar_for_state(self, state: NetworkState) -> float:
        if state in (NetworkState.DOWN, NetworkState.DEGRADED):
            return self.fast_scalar
        return self.slow_scalar

    def next_sleep(self, *, elapsed: float, state: NetworkState) -> float:
        interval = self.interval_for_state(state)
        jittered = interval + random.uniform(-self.jitter, self.jitter)
        return max(0.0, jittered - elapsed)
