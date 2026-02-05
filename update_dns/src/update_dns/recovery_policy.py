from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RecoveryPolicy:
    """
    Immutable policy describing when escalation is allowed and
    how destructive recovery is rate-limited.

    • Encodes intent and risk tolerance
    • No hardware knowledge
    • No side effects
    """

    # ─── Runtime wiring (composition root) ───
    cycle_interval_s: int
    fast_poll_scalar: float

    # ─── Expected infrastructure behavior ───
    expected_network_recovery_s: int = 180
    escalation_buffer_s: int = 60

    # ─── Physical recovery guardrails ───
    reboot_settle_delay_s: int = 30
    recovery_cooldown_s: int = 1800

    @property
    def escalation_delay_s(self) -> int:
        return self.expected_network_recovery_s + self.escalation_buffer_s

    @property
    def fast_poll_nominal_interval_s(self) -> float:
        return self.cycle_interval_s * self.fast_poll_scalar

    @property
    def max_consecutive_not_ready_cycles(self) -> int:
        return math.ceil(
            self.escalation_delay_s / self.fast_poll_nominal_interval_s
        )
