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
from .infra_agent import NetworkState, NetworkWatchdog


def main_loop(
        local_time: TimeService,
        policy: SchedulingPolicy,
        watchdog: NetworkWatchdog
    ):
    """
    Supervisor loop for continuous network monitoring and self-healing.

    This function repeatedly executes the `watchdog.run_cycle()` according to
    the schedule defined by `policy`. It handles exceptions, logs detailed
    network state, and enforces timing between cycles.

    Responsibilities:
        - Invoke the network watchdog to check LAN/WAN health.
        - Capture and return the resulting NetworkState for logging and metrics.
        - Handle unexpected exceptions gracefully, mapping them to NetworkState.ERROR.
        - Log the current network state with human-readable labels.
        - Respect the runtime scheduling policy (intervals, drift correction).
        - Sleep for the remaining interval time before the next cycle.

    Args:
        policy: SchedulingPolicy instance controlling loop timing.
        watchdog: NetworkWatchdog instance performing network checks
                  and self-healing actions.

    Notes:
        - NetworkState captures LAN/WAN/Router health and transient issues.
        - Logs include both state and sleep interval for observability.
        - Designed for 24/7 unattended operation with resilient recovery.    
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
            state = watchdog.evaluate_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during evaluate_cycle: {e}")
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
                meta=f"loop_rtt={loop_rtt_ms:.1f}ms | sleeping={remaining:.2f}s"
            )
        else:
            tlog(
                "🛜", 
                "STATE", 
                f"{state.label}",
                meta=f"loop_rtt={loop_rtt_ms:.1f}ms | sleeping={remaining:.2f}s"
            )

        time.sleep(remaining)
        loop += 1

def main():
    """
    Entry point for the network maintenance application.

    Configures logging and starts the supervisor loop.
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
    watchdog = NetworkWatchdog()
    
    main_loop(local_time, policy, watchdog)

if __name__ == "__main__":
    main()
