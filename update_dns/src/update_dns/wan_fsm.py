# --- Standard library imports ---
from enum import Enum, auto


class WanVerdict(Enum):
    STABLE = auto()
    WARMING = auto()
    UNREACHABLE = auto()

class WanFSM:
    """
    Tiny WAN confidence state machine.

    Invariants:
      - consec_fails increments only on UNREACHABLE verdicts
      - consec_fails resets only on STABLE verdicts
      - FSM does not perform network I/O — only reasons about results
    """

    def __init__(self, max_consec_fails: int):
        self.max_consec_fails = max_consec_fails
        self.consec_fails = 0

    def transition(self, verdict: WanVerdict) -> bool:
        """
        Apply a WAN verdict for this cycle.

        Returns:
            True if recovery escalation should trigger.
        """
        if verdict == WanVerdict.UNREACHABLE:
            self.consec_fails += 1
            return self.consec_fails >= self.max_consec_fails

        if verdict == WanVerdict.STABLE:
            self.consec_fails = 0

        # WARMING intentionally does not mutate counters
        return False
