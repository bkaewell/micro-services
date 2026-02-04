# ─── Standard library imports ───
import sys
import time
import logging
from enum import Enum, auto

# ─── Project imports ───
from .config import config
from .telemetry import tlog
from .bootstrap import bootstrap
from .recovery_policy import RecoveryPolicy
from .ddns_controller import DDNSController
from .logger import get_logger, setup_logging
from .scheduling_policy import SchedulingPolicy
from .recovery_controller import RecoveryController
from .readiness import ReadinessState, ReadinessController


class SupervisorState(Enum):
    """
    Health of a single supervisor loop iteration.

    • OK    — cycle completed without error
    • ERROR — unhandled exception occurred

    Used for telemetry only; does not control scheduling or recovery.
    """
    OK = auto()
    ERROR = auto()

    def __str__(self) -> str:
        return self.name

SUPERVISOR_EMOJI = {
    SupervisorState.OK:    "💚",
    SupervisorState.ERROR: "💣",
}

def run_supervisor_loop(
        scheduler: SchedulingPolicy,
        ddns: DDNSController
    ) -> None:
    """
    Top-level supervisor loop.

    Responsibilities:
    • Run the DDNS control cycle
    • Capture and log unhandled failures
    • Delegate timing decisions to the scheduler
    • Maintain steady cadence for long-running operation

    Notes:
    • This loop never exits
    • Exceptions are contained and surfaced via telemetry
    • Scheduling is adaptive to avoid API abuse and tight loops
    """

    logger = get_logger("run_supervisor_loop")
    readiness = ReadinessState.INIT
    
    # Intentional infinite loop - lifecycle managed externally by Docker
    while True:
        start = time.monotonic()
        supervisor_state = SupervisorState.OK

        try:
            readiness = ddns.run_cycle()
        except Exception as e:
            logger.exception(f"Unhandled exception during run_control_cycle: {e}")
            supervisor_state = SupervisorState.ERROR

        # Adaptive Polling Engine (APE): compute next poll interval
        elapsed = time.monotonic() - start
        decision = scheduler.next_schedule(
            elapsed=elapsed, 
            state=readiness
        )

        if supervisor_state == SupervisorState.ERROR:
            tlog(
                SUPERVISOR_EMOJI[supervisor_state], 
                "SUPERVISOR", 
                supervisor_state.name, 
                primary="observer failure"
            )

        tlog(
            "🐾",
            "SCHEDULER",
            "CADENCE",
            primary=str(decision.poll_speed),
            meta=f"sleep={decision.sleep_for:.0f}s | jitter={decision.jitter:.0f}s\n"
        )

        time.sleep(decision.sleep_for)

def main() -> None:
    """
    Application entry point.

    • Initialize logging and runtime configuration
    • Bootstrap system capabilities
    • Wire policies and controllers
    • Hand off control to the supervisor loop

    After this point, the process is expected to run indefinitely.
    """

    setup_logging(level=getattr(logging, config.LOG_LEVEL))
    logger = get_logger("main")

    logger.info("🚀 Starting Cloudflare DDNS Agent")
    logger.debug(f"Python version: {sys.version}")

    capabilities = bootstrap()

    allow_physical_recovery = config.ALLOW_PHYSICAL_RECOVERY
    plug_ip = config.Hardware.PLUG_IP

    # ─── Policies (stateless / config-driven) ───
    scheduler = SchedulingPolicy()
    recovery_policy = RecoveryPolicy()




    # ─── Controllers (stateful) ───
    readiness = ReadinessController()
    recovery = RecoveryController(
        policy=recovery_policy,
        allow_physical_recovery=allow_physical_recovery,
        plug_ip=plug_ip
    )
    ddns = DDNSController(
        readiness=readiness,
        recovery=recovery,
    )

    logger.info("Entering supervisor loop...\n")
    run_supervisor_loop(scheduler, ddns)

if __name__ == "__main__":
    main()
