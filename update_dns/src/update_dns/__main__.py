# --- Standard library imports ---
import sys
import time
import logging

# --- Project imports ---
from .config import Config
from .telemetry import tlog
from .time_service import TimeService
from .logger import get_logger, setup_logging
from .bootstrap import validate_runtime_config
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
    network_state = NetworkState.DOWN
    loop = 1

    while True:
        start = time.monotonic()

        # --- Heartbeat (local only, no network dependency) ---
        dt_local, _ = local_time.now_local()
        heartbeat = local_time.heartbeat_string(dt_local)
        tlog("🔁", "LOOP", "START", primary=heartbeat, meta=f"loop={loop}")

        try:
            network_state = agent.update_network_health()
        except Exception as e:
            logger.exception(f"Unhandled exception during run_control_cycle: {e}")
            #network_state = NetworkState.ERROR

        # Compute sleep interval
        elapsed = time.monotonic() - start
        elapsed_ms = elapsed * 1000
        sleep_for = scheduling_policy.next_sleep(elapsed=elapsed, state=network_state)

        if network_state == NetworkState.UP:
            tlog(
                NETWORK_EMOJI[network_state], 
                "NET_HEALTH", 
                network_state.name, 
                primary="ALL SYSTEMS NOMINAL 🐾🌤️ ",
                meta=f"full_rtt={elapsed_ms:.1f}ms | sleep={sleep_for:.1f}s\n"
            )
        else:
            tlog(
                NETWORK_EMOJI[network_state], 
                "NET_HEALTH", 
                network_state.name,
                meta=f"full_rtt={elapsed_ms:.1f}ms | sleep={sleep_for:.1f}s\n"
            )

        time.sleep(sleep_for)
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
    logger.info("🚀 Starting Network Health & DNS Reconciliation Agent")
    logger.debug(f"Python version: {sys.version}")

    validate_runtime_config()

    # Dependencies
    local_time = TimeService()
    scheduling_policy = SchedulingPolicy()
    agent = NetworkControlAgent()
    
    logger.info("Entering supervisor loop...")
    main_loop(local_time, scheduling_policy, agent)

if __name__ == "__main__":
    main()
