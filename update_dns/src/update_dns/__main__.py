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
from .infra_agent import NetworkState, NetworkControlAgent


def main_loop(
        local_time: TimeService,
        policy: SchedulingPolicy,
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
    state = NetworkState.UNKNOWN
    loop = 1

    while True:
        start = time.monotonic()

        # --- Heartbeat (local only, no network dependency) ---
        dt_local, _ = local_time.now_local()
        heartbeat = local_time.heartbeat_string(dt_local)
        tlog("🔁", "LOOP", "START", primary=heartbeat, meta=f"loop={loop}")

        try:
            state = agent.run_control_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during run_control_cycle: {e}")
            state = NetworkState.ERROR

        # Compute sleep interval
        loop_rtt = time.monotonic() - start
        loop_rtt_ms = loop_rtt * 1000
        remaining = policy.next_sleep(loop_rtt)

        if state == NetworkState.HEALTHY:
            tlog(
                "🛜", 
                "STATE", 
                f"{state.label}", 
                primary="ALL SYSTEMS NOMINAL 🐾🌤️ ",
                meta=f"loop_rtt={loop_rtt_ms:.1f}ms | sleeping={remaining:.2f}s\n"
            )
        else:
            tlog(
                "🛜", 
                "STATE", 
                f"{state.label}",
                meta=f"loop_rtt={loop_rtt_ms:.1f}ms | sleeping={remaining:.2f}s\n"
            )

        time.sleep(remaining)
        loop += 1

def main():
    """
    Entry point for the autonomous network control agent.

    Sets up observability, validates configuration, and launches the 
    resilient, self-healing supervisor loop that monitors LAN/WAN, 
    stabilizes public IP, and reconciles Cloudflare DNS in real time.
    Designed for production-grade reliability even on a home network.
    """

    # Setup logging policy
    setup_logging(level=getattr(logging, Config.LOG_LEVEL))
    logger = get_logger("main")
    logger.info("🚀 Starting Cloudflare DNS Reconciliation Infra Agent")
    logger.debug(f"Python version: {sys.version}")

    validate_runtime_config()

    # Time
    local_time = TimeService()
    
    # Policy
    policy = SchedulingPolicy()    

    # Core infra agent
    agent = NetworkControlAgent()
    
    main_loop(local_time, policy, agent)

if __name__ == "__main__":
    main()
