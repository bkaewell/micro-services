# ─── Standard library imports ───
import time
import requests

# ─── Project imports ───
from .telemetry import tlog
from .utils import ping_host
from .readiness import ReadinessState
from .recovery_policy import RecoveryPolicy


class RecoveryController:
    """
    Physical recovery orchestrator.

    Responsibilities:
    • Track sustained NOT_READY conditions
    • Enforce escalation thresholds and cooldown guardrails
    • Execute a single physical recovery action when permitted
    • Emit clear, operator-grade telemetry

    Non-responsibilities:
    • No readiness decisions
    • No network health inference
    • No retries or adaptive behavior
    """
    # ─── Class Constants ───
    SMART_PLUG_HTTP_TIMEOUT_S: float = 2.0  # LAN device: fast-fail by design

    def __init__(
        self,
        policy: RecoveryPolicy,
        allow_physical_recovery: bool,
        plug_ip: str | None,
    ):
        # ─── Dependencies / Configuration ───        
        self.policy = policy
        self.plug_ip = plug_ip

        # ─── Capability Gates ───        
        self.allow_physical_recovery = allow_physical_recovery

        # ─── Runtime State ───
        # Consecutive NOT_READY cycles (used for escalation)
        self.not_ready_streak: int = 0

        # ─── Recovery Guardrails ───
        self.last_recovery_time: float = 0.0  # epoch → first recovery allowed immediately

    def _plug_available(self) -> bool:
        return ping_host(self.plug_ip).success

    def observe(self, readiness: ReadinessState) -> None:
        """
        Observe the latest readiness verdict and update internal streaks.
        """
        if readiness == ReadinessState.NOT_READY:
            self.not_ready_streak += 1
        else:
            self.not_ready_streak = 0

    def maybe_recover(self) -> bool:
        """
        Attempt recovery if escalation thresholds are met and permitted.

        Returns:
            True if a recovery action was executed successfully.
            False otherwise (including suppression).
        """
        if not self.allow_physical_recovery:
            self._emit_suppressed("disabled by config")
            return False
        
        if not self._plug_available():
            self._emit_suppressed("smart plug unavailable")
            return False

        if self.not_ready_streak < self.policy.max_consecutive_down_before_escalation:
            return False

        now = time.monotonic()
        since_last = now - self.last_recovery_time

        if since_last < self.policy.recovery_cooldown_s:
            self._emit_suppressed(
                "cooldown active",
                meta=f"last_attempt={int(since_last)}s | window={self.policy.recovery_cooldown_s}s",
            )
            return False
        
        return self._execute_recovery(now)

    def _execute_recovery(self, now: float) -> bool:
        """
        Execute a single physical recovery attempt.
        """
        tlog(
            "🔴",
            "RECOVERY",
            "TRIGGER",
            primary="power-cycle edge device",
            meta=f"reboot_delay={self.policy.reboot_settle_delay_s}s",
        )

        # ─── Execute recovery ───
        success = self._power_cycle_edge()

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "COMPLETE" if success else "FAILED",
            primary="power-cycle attempt",
        )

        # Update last recovery timestamp only on successful command execution
        if success:
            self.last_recovery_time = now
            self.not_ready_streak = 0

        return success

    def _power_cycle_edge(self) -> bool:
        """
        Perform a single OFF → delay → ON power cycle of the edge device.

        Design:
        - LAN-only, fast-fail semantics (no retries)
        - Short, fixed HTTP timeout (device either responds or it doesn’t)
        - Success = command issued, not device verified online

        Returns:
            True if power cycle commands were successfully issued.
        """

        try:
            # Power OFF
            requests.get(
                f"http://{self.plug_ip}/relay/0?turn=off",
                timeout=RecoveryController.SMART_PLUG_HTTP_TIMEOUT_S,
            ).raise_for_status()
            self.logger.debug("Smart plug powered OFF")
            time.sleep(self.policy.reboot_settle_delay_s)

            # Power ON
            requests.get(
                f"http://{self.plug_ip}/relay/0?turn=on",
                timeout=RecoveryController.SMART_PLUG_HTTP_TIMEOUT_S,
            ).raise_for_status()
            self.logger.debug("Smart plug powered ON")

            return True

        except requests.RequestException:
            self.logger.exception("Failed to communicate with smart plug")
            return False

        except Exception:
            self.logger.exception("Unexpected error during recovery")
            return False

    # ──────────────────────────────────────────────────────────────
    # Telemetry helpers
    # ──────────────────────────────────────────────────────────────

    def _emit_suppressed(self, reason: str, meta: str | None = None) -> None:
        tlog(
            "🟡",
            "RECOVERY",
            "SUPPRESSED",
            primary=reason,
            meta=meta or f"down_count={self.not_ready_streak}",
        )
