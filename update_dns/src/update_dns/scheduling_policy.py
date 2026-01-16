# --- Standard library imports ---
import random

# --- Project imports ---
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
        self.enforce_policy = config.ENFORCE_TTL_POLICY
        self.logger = get_logger("scheduling_policy")

    def interval_for_state(self, state: NetworkState) -> int:
        """
        Returns the effective interval (seconds) for the given network state.
        """

        scalar = self._scalar_for_state(state)
        requested = int(self.base_interval * scalar)

        min_safe = self.min_ttl + self.polling_jitter

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
        jittered = interval + random.uniform(-self.polling_jitter, self.polling_jitter)
        return max(0.0, jittered - elapsed)
