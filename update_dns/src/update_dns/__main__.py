# ─── Standard library imports ───
import sys
import time
import logging
from enum import Enum, auto

# ─── Project imports ───
from .config import Config
from .telemetry import tlog
from .cache import store_uptime
from .bootstrap import bootstrap
from .logger import get_logger, setup_logging
from .scheduling_policy import SchedulingPolicy
from .infra_agent import ReadinessState, READINESS_EMOJI, DDNSController


class SupervisorState(Enum):
    """
    Canonical representation of supervisor loop health.

    States are intentionally minimal:
        OK    → loop completed without error
        ERROR → unhandled exception occurred
    """    
    OK = auto()
    ERROR = auto()

    def __str__(self) -> str:
        return self.name

SUPERVISOR_EMOJI = {
    SupervisorState.OK:    "💚",
    SupervisorState.ERROR: "💣",
}

def main_loop(
        scheduling_policy: SchedulingPolicy,
        ddns: DDNSController
    ):
    """
    Supervisor loop for autonomous network control, dynamic DNS reconciliation,
    and self-healing infrastructure.

    Built to maintain a dynamic WireGuard VPN, this agent monitors LAN/WAN 
    health, stabilizes the public IP, and updates Cloudflare DNS only once WAN 
    stability is confirmed. As a stretch goal, it can trigger physical recovery
    if the network becomes unresponsive. Scheduling includes subtle timing 
    adjustments to avoid Cloudflare API rate limits while maximizing telemetry 
    and observability.

    Features:
        - Continuously run the NetworkControlAgent evaluation cycle
        - Sync Cloudflare DNS only when WAN and IP are verified stable
        - Maintain telemetry and ReadinessState logging for long-running operation
        - Enforce drift-aware scheduling to balance consistency and API friendliness
        - Escalate physical WAN recovery after repeated failures
    """

    logger = get_logger("main_loop")
    network_state = ReadinessState.INIT
    loop = 1

    while True:
        start = time.monotonic()
        heartbeat = heartbeat = time.strftime("%a %b %d %Y")
        tlog("🔁", "LOOP", "START", primary=heartbeat, meta=f"loop={loop}")

        try:
            # Update Network Health / Reconcile DNS:
            network_state = ddns.reconcile()
            supervisor_state = SupervisorState.OK
        except Exception as e:
            logger.exception(f"Unhandled exception during run_control_cycle: {e}")
            supervisor_state = SupervisorState.ERROR

        # ─── Uptime Cycle Counting ───
        ddns.uptime.total += 1
        if network_state == ReadinessState.READY:
            ddns.uptime.up += 1
        
        # Optional: save every 50 measurements (low I/O)
        #if self.uptime.total % 50 == 0:
        # Align with CACHE_MAX_AGE_S ~3600 seconds?
        store_uptime(ddns.uptime)

        # Adaptive Polling Engine (APE): compute next poll interval
        elapsed = time.monotonic() - start
        elapsed_ms = elapsed * 1000
        decision = scheduling_policy.next_schedule(
            elapsed=elapsed, 
            state=network_state
        )

        tlog(
            "⏱️ ",
            "SCHEDULER",
            "CADENCE",
            primary=str(decision.poll_speed),
            meta=f"sleep={decision.sleep_for:.0f}s | jitter={decision.jitter:.0f}s"
        )

        if supervisor_state == SupervisorState.ERROR:
            tlog(
                SUPERVISOR_EMOJI[supervisor_state], 
                "SUPERVISOR", 
                supervisor_state.name, 
                primary="observer failure"
            )

        tlog(
            READINESS_EMOJI[network_state], 
            "NET_STATUS", 
            network_state.name, 
            primary="steady-state" if network_state == ReadinessState.READY else "recovery",
            meta=f"LOOP={elapsed_ms:.0f}ms | UPTIME={ddns.uptime}\n"
        )

        time.sleep(decision.sleep_for)
        loop += 1

def main():
    """
    Application entry point for the autonomous network control agent.

    Initializes observability, validates runtime configuration, and composes
    the production-grade control loop responsible for WAN health assessment,
    public IP stabilization, and Cloudflare DNS reconciliation. Although built
    for a home network, the system is engineered with real-world reliability,
    failure handling, and operational discipline in mind.
    """

    setup_logging(level=getattr(logging, Config.LOG_LEVEL))
    logger = get_logger("main")
    logger.info("🚀 Starting Network Health & Cloudflare DDNS Reconciliation Agent")
    logger.debug(f"Python version: {sys.version}")

    capabilities = bootstrap()

    # Dependencies
    scheduling_policy = SchedulingPolicy()
    ddns = DDNSController(capabilities)
    
    logger.info("Entering supervisor loop...\n")
    main_loop(scheduling_policy, ddns)

if __name__ == "__main__":
    main()
