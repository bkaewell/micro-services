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

    Repeatedly executes the watchdog evaluation cycle according to the
    configured scheduling policy, handling exceptions and enforcing
    consistent timing between iterations.

    Responsibilities:
        - Invoke the NetworkWatchdog for health evaluation
        - Capture and log the resulting NetworkState
        - Handle unexpected exceptions gracefully
        - Enforce scheduling intervals and drift correction

    Notes:
        - Designed for long-running, unattended operation
        - NetworkState.ERROR represents unexpected internal failures    
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
    Application entry point for the network monitoring agent.

    Initializes logging, validates runtime configuration, and starts
    the supervisor loop.
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
