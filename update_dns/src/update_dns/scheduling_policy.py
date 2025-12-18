# --- Standard library imports ---
import random

# --- Project imports ---
from .config import Config
from .logger import get_logger


# --- Scheduling policy constants ---
DNS_UPDATE_JITTER = 5  # seconds (fixed, internal safety margin)

class SchedulingPolicy:
    def __init__(self):
        self.requested_interval = Config.CYCLE_INTERVAL
        self.min_ttl = Config.CLOUDFLARE_MIN_TTL
        self.enforce_policy = Config.ENFORCE_TTL_POLICY
        self.jitter = DNS_UPDATE_JITTER
        self.logger = get_logger("scheduling_policy")

    def effective_runtime_interval(self) -> int:
        """
        Returns the final runtime interval that will be used for scheduling.

        When enforcement is enabled, guarantees:
            base_interval - jitter >= MIN_TTL
        """
        
        min_safe = self.min_ttl + self.jitter

        # --- Production enforcement ---
        if self.enforce_policy:
            if self.requested_interval < min_safe:
                self.logger.warning(
                    "CYCLE_INTERVAL=%ss is below safe minimum (%ss). Enforcing %ss.",
                    self.requested_interval,
                    min_safe,
                    min_safe,
                )
                return min_safe
            return self.requested_interval

        # --- Testing mode: warn if unsafe, but do not enforce ---
        if self.requested_interval < self.min_ttl:
            self.logger.warning(
                "CYCLE_INTERVAL=%ss is below TTL minimum (%ss). Allowed because ENFORCE_TTL_POLICY=false.",
                self.requested_interval,
                self.min_ttl,
            )

        return self.requested_interval

    def next_sleep(self, elapsed: float) -> float:
        return max(
            0.0,
            self.effective_runtime_interval()
            + random.uniform(-self.jitter, self.jitter)
            - elapsed,
        )
