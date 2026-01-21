# ─── Future imports ───
from __future__ import annotations

# ─── Standard library imports ───
import math
from dataclasses import dataclass

# ─── Project imports ───
from .config import config


@dataclass(frozen=True)
class RecoveryPolicy:
    """
    Policy governing escalation and destructive self-healing behavior
    for network recovery.

    This class encodes *intent* and *risk tolerance*, not hardware wiring.
    All values are chosen to bias toward conservative recovery and to
    prevent unnecessary physical interventions (e.g., power cycling).
    """

    # ─── Expected infrastructure behavior ───

    # Worst-case time for ONT/modem + router + WAN to recover naturally
    expected_network_recovery_s: int = 180  # ~3 minutes

    # Additional buffer to tolerate transient ISP or routing instability
    escalation_buffer_s: int = 60  # ~1 minute

    # ─── Physical recovery guardrails ───

    # Minimum time to wait after issuing a reboot command
    reboot_settle_delay_s: int = 30

    # Cooldown window to prevent repeated destructive actions
    recovery_cooldown_s: int = 1800  # 30 minutes

    # ─── Derived policy values (computed) ───

    @property
    def escalation_delay_s(self) -> int:
        """
        Total sustained DOWN time required before escalation is permitted.
        """
        return self.expected_network_recovery_s + self.escalation_buffer_s

    @property
    def fast_poll_nominal_interval_s(self) -> float:
        """
        Nominal fast polling interval (excluding jitter).

        Jitter is intentionally excluded here to bias escalation conservatively
        by assuming the *fastest* plausible confirmation cadence.
        """
        return config.CYCLE_INTERVAL_S * config.FAST_POLL_SCALAR
    
    @property
    def max_consecutive_down_before_escalation(self) -> int:
        """
        Number of consecutive DOWN observations required before escalation.

        Computed using the nominal fast polling interval to avoid premature
        escalation caused by jitter-induced timing compression.
        """
        return math.ceil(
            self.escalation_delay_s / self.fast_poll_nominal_interval_s
        )

    # ─── Introspection / debugging helpers ───────────────────────────────

    def summary(self) -> dict[str, int | float]:
        """
        Return a structured summary of the effective policy values.
        Useful for logs, telemetry, and startup diagnostics.
        """
        return {
            "expected_network_recovery_s": self.expected_network_recovery_s,
            "escalation_buffer_s": self.escalation_buffer_s,
            "escalation_delay_s": self.escalation_delay_s,
            "fast_poll_nominal_interval_s": self.fast_poll_nominal_interval_s,
            "max_consecutive_down_before_escalation":
                self.max_consecutive_down_before_escalation,
            "reboot_settle_delay_s": self.reboot_settle_delay_s,
            "recovery_cooldown_s": self.recovery_cooldown_s,
        }

# Global singleton instance
recovery_policy = RecoveryPolicy()
