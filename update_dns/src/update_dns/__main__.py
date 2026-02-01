# ─── Standard library imports ───
import sys
import time
import logging

# ─── Project imports ───
from .config import Config
from .telemetry import tlog
from .cache import store_uptime
from .bootstrap import bootstrap
from .time_service import TimeService
from .logger import get_logger, setup_logging
from .scheduling_policy import SchedulingPolicy
from .infra_agent import NetworkState, NETWORK_EMOJI, NetworkControlAgent


def main_loop(
        local_time: TimeService,
        scheduling_policy: SchedulingPolicy,
        agent: NetworkControlAgent
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
        - Maintain telemetry and NetworkState logging for long-running operation
        - Enforce drift-aware scheduling to balance consistency and API friendliness
        - Escalate physical WAN recovery after repeated failures
    """

    logger = get_logger("main_loop")
    network_state = NetworkState.INIT
    loop = 1

    while True:
        start = time.monotonic()

        # ─── Heartbeat (local only, no network dependency) ───
        dt_local, _ = local_time.now_local()
        heartbeat = local_time.heartbeat_string(dt_local)
        tlog("🔁", "LOOP", "START", primary=heartbeat, meta=f"loop={loop}")

        try:
            # Update Network Health / Reconcile DNS:
            network_state = agent.update_network_health()
        except Exception as e:
            logger.exception(f"Unhandled exception during run_control_cycle: {e}")
            network_state = NetworkState.ERROR

        # ─── Uptime Cycle Counting ───
        agent.uptime.total += 1
        if network_state == NetworkState.UP:
            agent.uptime.up += 1
        
        # Optional: save every 50 measurements (low I/O)
        #if self.uptime.total % 50 == 0:
        # Align with CACHE_MAX_AGE_S ~3600 seconds?
        store_uptime(agent.uptime)

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

        tlog(
            NETWORK_EMOJI[network_state], 
            "NET_STATUS", 
            network_state.name, 
            primary="steady-state" if network_state == NetworkState.UP else "recovery",
            meta=f"LOOP={elapsed_ms:.0f}ms | UPTIME={agent.uptime}\n"
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
    local_time = TimeService()
    scheduling_policy = SchedulingPolicy()
    agent = NetworkControlAgent(capabilities)
    
    logger.info("Entering supervisor loop...\n")
    main_loop(local_time, scheduling_policy, agent)

if __name__ == "__main__":
    main()
