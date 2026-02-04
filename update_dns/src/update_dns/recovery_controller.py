# ─── Standard library imports ───
import time
import requests

# ─── Project imports ───
from .config import config
from .telemetry import tlog
from .utils import ping_host
from .readiness import ReadinessState
from .bootstrap import EnvCapabilities
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

    def __init__(
        self,
        policy: RecoveryPolicy,
        #enabled: bool,
        capabilities: EnvCapabilities,
        #plug_ip: str | None,
    ):
        self.policy = policy
        #self.enabled = enabled
        self.enabled = False
        #self.plug_ip = plug_ip
        self.plug_ip = config.Hardware.PLUG_IP
        self.physical_recovery_available = capabilities.physical_recovery_available

        # ─── Failure & Escalation Tracking ───
        self.not_ready_streak: int = 0

        # ─── Recovery Guardrails ───
        self.last_recovery_time: float = 0.0  # far in the past → first recovery allowed immediately

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
        if not self.enabled:
            self._emit_suppressed("disabled by config")
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

        # Optional pre-check (telemetry only)
        plug_ok_before = ping_host(self.plug_ip).success

        tlog(
            "🟡" if plug_ok_before else "🔴",
            "EDGE",
            "REACHABLE" if plug_ok_before else "UNREACHABLE",
            primary="pre-recovery check",
            meta=f"smart_plug_ip={self.plug_ip}"
        )

        # ─── Execute recovery ───
        success = self._power_cycle_edge()

        plug_ok_after = ping_host(self.plug_ip).success

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "COMPLETE" if success else "FAILED",
            primary="power-cycle attempt",
            meta=f"plug_pre={plug_ok_before} | plug_post={plug_ok_after}",
        )

        # Update last recovery timestamp only on successful command execution
        if success:
            self.last_recovery_time = now
            self.not_ready_streak = 0

        return success

    def _power_cycle_edge(self) -> bool:
        """
        Perform a deterministic OFF → delay → ON power cycle of the network
        edge device.

        Policy-agnostic. Single-shot. No retries.
        """
        if not self.plug_ip:
            return False

        try:
            # Power OFF
            requests.get(
                f"http://{self.plug_ip}/relay/0?turn=off",
                timeout=config.API_TIMEOUT_S,
            ).raise_for_status()
            self.logger.debug("Smart plug powered OFF")
            time.sleep(self.policy.reboot_settle_delay_s)

            # Power ON
            requests.get(
                f"http://{self.plug_ip}/relay/0?turn=on",
                timeout=config.API_TIMEOUT_S,
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
