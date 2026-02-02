# ─── Standard library imports ───
import time
from enum import Enum, auto
from typing import Optional

# ─── Third-party imports ───
import requests

# ─── Project imports ───
from .config import config
from .telemetry import tlog
from .logger import get_logger
from .cloudflare import CloudflareClient
from .bootstrap import EnvCapabilities
from .recovery_policy import recovery_policy
from .utils import ping_host, verify_wan_reachability, get_ip, doh_lookup, IPResolutionResult
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip, CacheLookupResult, load_uptime
#from .db import log_metrics


class ReadinessState(Enum):
    """
    Canonical readiness classification for for network-dependent side effects.

    Readiness answers one question:
        "Is it safe to act?"

    States are monotonic:
        INIT / NOT_READY → PROBING → READY
        Any verified failure → NOT_READY

    READY implies:
      - WAN path verified
      - Public IP stable
      - DNS authority trustworthy

    NOT_READY implies:
      - Observation only
      - No external mutation allowed
    """
    INIT = auto()
    PROBING = auto()
    READY = auto()
    NOT_READY = auto()

    def __str__(self) -> str:
        return self.name

READINESS_EMOJI = {
    ReadinessState.INIT:      "⚪",
    ReadinessState.PROBING:   "🟡",
    ReadinessState.READY:     "💚",
    ReadinessState.NOT_READY: "🔴",
}

class ReadinessController:
    """
    Deterministic readiness controller backed by a monotonic finite-state machine.

    Acts as the single source of truth for whether the system is safe to perform
    external side effects (DNS updates, recovery actions).

    Design principles:
    • Monotonic promotion: INIT / NOT_READY → PROBING → READY
    • Immediate fail-fast demotion on any verified WAN failure
    • Promotion explicitly gated by external stability signals
    • No internal counters, timers, or hysteresis
    • Pure, deterministic logic — trivial to test and reason about

    Inspired by Kubernetes-style readiness controllers, simplified for
    single-node, real-world network environments.
    """

    def __init__(self):
        self.state: ReadinessState = ReadinessState.INIT

    def _demote(self) -> None:
        self.state = ReadinessState.NOT_READY

    def advance(
            self, 
            wan_path_ok: bool, 
            allow_promotion: bool = True,
        ) -> ReadinessState:
        """
        Network health is governed by a monotonic finite state machine (FSM):
        - Promotions proceed only INIT/NOT_READY → PROBING → READY; regressions never skip levels.
        - Any verified WAN failure triggers an immediate, fail-fast demotion to NOT_READY.
        - Promotion to READY is explicitly gated by external stability signals (IP consistency).
        - PROBING is a probationary hold state, never operational readiness.
        - All advances are deterministic and evaluated once per control loop cycle.
        """
        if not wan_path_ok:
            self._demote()
            return self.state

        match self.state:
            case ReadinessState.INIT | ReadinessState.NOT_READY:
                self.state = ReadinessState.PROBING

            case ReadinessState.PROBING if allow_promotion:
                self.state = ReadinessState.READY

            case _:
                pass  # READY stays READY

        return self.state

class DDNSController:
    """
    Autonomous control-plane agent responsible for WAN health assessment,
    public IP stabilization, and Cloudflare DNS reconciliation.

    Designed for low-noise operation under healthy conditions, the agent
    builds confidence in network stability across cycles and performs
    corrective actions only after sustained failure is confirmed by policy.
    Although deployed on a home network, it is engineered with real-world
    reliability, observability, and failure isolation in mind.

    Features:
        - Observes LAN reachability, WAN path health, and public IP state
        - Promotes WAN health through a finite-state confidence model
        - Reconciles Cloudflare DNS only after stability is established
        - Escalates recovery actions when failure thresholds are exceeded
        - Emits a single authoritative ReadinessState per control cycle
    """

    def __init__(self, capabilities: EnvCapabilities):
        """
        Core autonomous network controller.

        Design principles:
        - Conservative startup (probationary, no assumptions)
        - Single source of truth for readiness (FSM)
        - Edge-triggered recovery with hard guardrails
        """

        # ─── Observability & External Interfaces ─── 
        self.logger = get_logger("network_controller")
        self.cloudflare_client = CloudflareClient()

        # ─── Environment & Hardware Topology ─── 
        self.router_ip = config.Hardware.ROUTER_IP
        self.plug_ip = config.Hardware.PLUG_IP
        self.physical_recovery_available = capabilities.physical_recovery_available

        # ─── Policy & Control Parameters ─── 
        self.max_cache_age_s = config.MAX_CACHE_AGE_S
        self.promotion_confirmations_required = 2   # consecutive stable IPs required for READY

        # ─── Readiness Controller (single source of truth) ─── 
        self.readiness = ReadinessController()
        self.prev_readiness: ReadinessState = ReadinessState.INIT

        # ─── Promotion / Stability Tracking (Probation Logic) ───         
        self.last_public_ip: Optional[str] = None
        self.promotion_votes: int = 0   # consecutive confirmations
        
        # ─── Failure & Escalation Tracking ───         
        self.not_ready_streak: int = 0  # consecutive NOT_READY evaluations

        # ─── Recovery Guardrails ───
        self.last_recovery_time: float = 0.0  # far in the past → first recovery allowed immediately

        # ─── Metrics & Long-Lived Counters ───
        self.uptime = load_uptime()

        ##################
        # For testing only
        ##################
        self.count = 0
        self.flag = True

    def _record_ip_observation(self, public_ip: Optional[str]) -> bool:
        """
        Tracks public IP continuity to serve as a conservative promotion gate.

        Used exclusively by the FSM to prevent premature READY advances when
        secondary signals (public IP) are unstable.

        Semantics:
        • Any change/missing IP → reset stability counter
        • Identical consecutive IPs → increment counter
        • Returns True only after required consecutive matches

        Keeps the FSM clean by externalizing hysteresis — simple, deterministic,
        and focused on "has this IP been stable long enough?"
        """
        if not public_ip:
            self.promotion_votes = 0
            self.last_public_ip = None
            return False

        if public_ip == self.last_public_ip:
            self.promotion_votes += 1
        else:
            self.promotion_votes = 1
            self.last_public_ip = public_ip

        return self.promotion_votes >= self.promotion_confirmations_required

    def _on_not_ready_entry(self):
        """
        Epochal reset hook triggered exactly once on entry to NOT_READY.

        Ensures fresh evidence is required for recovery by:
        • Invalidating all prior promotion confidence
        • Clearing IP stability tracking
        • Forcing a clean slate after any verified failure
        """
        self.promotion_votes = 0
        self.last_public_ip = None


    def _log_readiness_change(
        self,
        prev: ReadinessState,
        current: ReadinessState,
        promotion_votes: Optional[int] = None,
    ):
        """
        Emit a single authoritative log line describing a readiness advance.
        """

        prev = prev or ReadinessState.INIT
        transition = f"{prev.name} → {current.name}"
        meta = []

        if prev == ReadinessState.PROBING and current == ReadinessState.READY:
            meta.append(
                f"confirmations={promotion_votes}/{self.promotion_confirmations_required}"
            )

        tlog(
            READINESS_EMOJI[current],
            "READINESS",
            "CHANGE",
            primary=transition,
            meta=" | ".join(meta) if meta else None,
        )

        # ─── Future Work ───
        # Send notification via 3rd party messaging app
        #  - Telegram's @BotFather API 
        #  - WhatsApp API??

    def _reconcile_dns(self, public_ip: str) -> None:
        """
        Reconciles Cloudflare DNS with the current public IP — only when safe.

        Called exclusively when ReadinessState is READY (stable, verified WAN).
        Enforces eventual consistency using a deliberate, layered approach:

        L1: Local cache check — fast no-op on match (zero external calls)
        L2: Authoritative DoH lookup — external truth without mutation
        L3: Targeted update — only on confirmed drift

        Key safety invariants:
        • Idempotent: safe to call repeatedly; converges without thrashing
        • Mutation-gated: never updates unless L2 shows real mismatch
        • Stability-first: runs only after consecutive IP + WAN confirmation

        This is the **single authoritative path** for DNS mutation in the agent.
        Keeps the system self-healing while minimizing API calls and risk.
        """

        # ─── L1 Cache (Cheap, local, fast no-op) ───
        # Only proceed to DoH if cache is absent, stale, or mismatched

        cache = load_cached_cloudflare_ip()

        cache_hit = cache.hit
        cache_fresh = cache_hit and (cache.age_s <= self.max_cache_age_s)
        cache_match = cache_fresh and (cache.ip == public_ip)

        if not cache_hit:
            cache_state = "MISS"
        elif not cache_fresh:
            cache_state = "EXPIRED"
        elif not cache_match:
            cache_state = "MISMATCH"
        else:
            cache_state = "HIT"

        tlog(
            {
                "HIT": "🟢",
                "MISMATCH": "🟡",
                "EXPIRED": "🟠",
                "MISS": "🔴",
            }[cache_state],
            "CACHE",
            cache_state,
            primary=f"age={cache.age_s:.0f}s" if cache_hit else "no cache",
            meta=(
                f"rtt={cache.elapsed_ms:.1f}ms"
            ) if cache_hit else None,
        )

        if cache_match:
            return  # Fast no-op: we trust the cache = DNS = current IP

        # ─── L2 DoH (Authoritative truth) ───
        doh = doh_lookup(self.cloudflare_client.dns_name)

        if doh.success and doh.ip == public_ip:
            tlog(
                "🟢",
                "DNS",
                "VERIFIED",
                primary=f"ip={doh.ip}",
                meta=f"rtt={doh.elapsed_ms:.0f}ms"
            )
            store_cloudflare_ip(public_ip)   # Safe: DoH confirmed current IP is what DNS has
            tlog("🟢", "CACHE", "REFRESHED", primary=f"ttl={self.max_cache_age_s}s")
            return

        # ─── L3 Mutation required ───
        result, elapsed_ms = self.cloudflare_client.update_dns(public_ip)
        store_cloudflare_ip(public_ip)       # Safe: we just wrote it
        #result.get("modified_on")
        
        meta=[]
        meta.append(f"rtt={elapsed_ms:.0f}ms")
        meta.append(f"desired={public_ip}")
        meta.append(f"ttl={self.cloudflare_client.ttl}s")
        tlog(
            "🟢",
            "CLOUDFLARE",
            "UPDATED",
            primary=f"dns={self.cloudflare_client.dns_name}",
            meta=" | ".join(meta) if meta else ""
        )
        tlog("🟢", "CACHE", "REFRESHED", primary=f"ttl={self.max_cache_age_s}s")

    def _power_cycle_edge(self) -> bool:
        """
        Perform a hard, out-of-band power cycle of the network edge device.

        This is the lowest-level physical remediation primitive — a simple,
        deterministic OFF → delay → ON sequence via smart relay.

        Design invariants:
        • Policy-agnostic: no health checks, no retries, no outcome inference
        • Single-shot: executes exactly once, reports success/failure only
        • Boundary: MUST be called only by higher-level orchestration

        Returns:
            True if the full relay command sequence completed successfully.
            False on any communication or execution error.
        """

        try:
            # Power OFF
            off = requests.get(
                f"http://{self.plug_ip}/relay/0?turn=off", 
                timeout=config.API_TIMEOUT_S
            )
            off.raise_for_status()
            self.logger.debug("Smart plug powered OFF")

            time.sleep(recovery_policy.reboot_settle_delay_s)

            # Power ON
            on = requests.get(
                f"http://{self.plug_ip}/relay/0?turn=on", 
                timeout=config.API_TIMEOUT_S
            )
            on.raise_for_status()
            self.logger.debug("Smart plug powered ON")

            return True

        except requests.RequestException:
            self.logger.exception("Failed to communicate with smart plug")
            return False
        except Exception:
            self.logger.exception("Unexpected error during recovery")
            return False

    def _initiate_recovery(self) -> bool:
        """
        Orchestrate a policy-approved physical recovery attempt.

        Invoked only after escalation thresholds are met and recovery is explicitly
        allowed by policy. Acts as a clean boundary between failure detection
        (ReadinessController) and physical action.

        Responsibilities:
        • Enforce cooldown guardrail to protect hardware
        • Emit clear, operator-grade telemetry before/after attempt
        • Execute one power-cycle via _power_cycle_edge()
        • Return simple boolean outcome

        Non-responsibilities:
        • No re-evaluation of network health
        • No retry/backoff (handled upstream)
        • No suppression logic beyond cooldown

        Returns:
            True if recovery command executed successfully.
            False otherwise (including cooldown suppression).
        """
        now = time.monotonic()
        
        # ─── Cooldown Guardrail ───
        time_since_last = now - self.last_recovery_time
        
        if time_since_last < recovery_policy.recovery_cooldown_s:
            tlog(
                "🔴",
                "RECOVERY",
                "SUPPRESSED",
                primary="cooldown active",
                meta=f"last_attempt={int(time_since_last)}s ago | window={recovery_policy.recovery_cooldown_s}s"
            )
            return False

        tlog(
            "🔴", 
            "RECOVERY", 
            "TRIGGER", 
            primary="power-cycle edge device",
            meta=f"smart_plug_ip={self.plug_ip} | reboot_delay={recovery_policy.reboot_settle_delay_s}s"
        )
    
        # Pre-check plug reachability (optional but useful for telemetry)
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

        # Post-check plug reachability (telemetry only, not decision factor)
        plug_ok_after = ping_host(self.plug_ip).success

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "COMPLETE" if success else "FAILED",
            primary="power-cycle attempt",
            meta=f"plug_pre={plug_ok_before} | plug_post={plug_ok_after}"
        )

        # Update last recovery timestamp only on successful command execution
        if success:
            self.last_recovery_time = now

        return success


    #********************************
    #********************************
    #********************************
    #********************************
    #********************************
    def _override_public_ip_for_test(
        self,
        public: IPResolutionResult,
    ) -> IPResolutionResult:
        
        if self.count % 3 == 0:
            self.flag = not self.flag
        
        if self.flag:
            return IPResolutionResult(
                ip="192.168.0.77",
                elapsed_ms=public.elapsed_ms,
                attempts=public.attempts,
                max_attempts=4,
                success=True,
            )
            ip: str | None

        return public

    #********************************
    #********************************
    #********************************
    #********************************
    #********************************


    def reconcile(self) -> ReadinessState:
        """
        Execute one complete control cycle: observe network signals, assess health,
        decide on actions, perform side-effects (when safe), and report telemetry.

        This is the agent's main heartbeat — called repeatedly in the supervisor loop.

        Core workflow (strict phase separation for clarity & testability):
        1. Observe   → Collect raw, unfiltered reachability signals (LAN, WAN path, public IP)
        2. Assess    → Feed primary signal into ReadinessController (single source of truth)
        3. Decide    → Check escalation thresholds & promotion gates
        4. Act       → Trigger safe side-effects: DNS reconciliation, physical recovery
        5. Report    → Emit high-signal telemetry (detailed when degraded/down, minimal when READY)

        Key design principles:
        • FSM is the sole authority on health state — deterministic & monotonic
        • Side-effects are strictly gated by READY state + stability checks
        • Fail-fast & safe-by-default — no action without fresh evidence
        • Boring READY states are kept quiet; detailed logs only when building trust or failing

        Returns the updated ReadinessState after this cycle.
        """

        # ─── Observe: collect raw signals (no policy, no interpretation) ───
        # LAN reachability (weak signal; informational only)
        lan = ping_host(self.router_ip)
        tlog(
            "🟢" if lan.success else "🔴",
            "ROUTER",
            "UP" if lan.success else "DOWN",
            primary=f"ip={self.router_ip}",
            meta=f"rtt={lan.elapsed_ms:.0f}ms"
        )

        # WAN path reachability (strong signal; feeds Network Health FSM)
        host="1.1.1.1"
        port=443
        wan_path = verify_wan_reachability(host=host, port=port)
        meta = []
        meta.append(f"rtt={wan_path.elapsed_ms:.0f}ms")
        if wan_path.success:
            meta.append("tls=ok")
        tlog(
            "🟢" if wan_path.success else "🔴",
            "WAN_PATH",
            "UP" if wan_path.success else "DOWN",
            primary=f"dest={host}:{port}",
            meta=" | ".join(meta) if meta else None
        )


        # ─── Policy: IP stability check (only when we have some confidence) ───
        allow_promotion = False
        public = None

        if (
            self.readiness.state is not ReadinessState.NOT_READY
            and wan_path.success
        ):
            public = get_ip()
            #public = self._override_public_ip_for_test(public)  # DEBUG hook
            #self.count += 1

            tlog(
                "🟢" if public.success else "🔴",
                "PUBLIC_IP",
                "OK" if public.success else "FAIL",
                primary=f"ip={public.ip}",
                meta=f"rtt={public.elapsed_ms:.0f}ms"
            )

            # Determine whether promotion (PROBING → READY) is allowed
            if public.success and self.readiness.state == ReadinessState.PROBING:
                allow_promotion = self._record_ip_observation(public.ip)

        else:
            tlog("🟡", "PUBLIC_IP", "SKIPPED")
        

        # ─── Assess: FSM advance (single source of truth) ───
        prev_readiness = self.prev_readiness
        readiness = self.readiness.advance(
            wan_path_ok=wan_path.success,
            allow_promotion = allow_promotion
        )

        # Transition telemetry (single line, high signal)
        if prev_readiness != readiness:
            self._log_readiness_change(
                prev=prev_readiness,
                current=readiness,
                promotion_votes=self.promotion_votes,
            )    


        # ─── Decide + Act: edge-triggered actions ───
        if readiness == ReadinessState.NOT_READY and self.prev_readiness != ReadinessState.NOT_READY:
            self._on_not_ready_entry()

        self.prev_readiness = readiness


        # ─── Decide: escalation check ───
        # Escalation counter increments only during NOT_READY
        if readiness == ReadinessState.NOT_READY:
            self.not_ready_streak += 1
        else:
            self.not_ready_streak = 0

        escalate = (
            readiness == ReadinessState.NOT_READY
            and self.not_ready_streak >= recovery_policy.max_consecutive_down_before_escalation
        )
        failures_at_decision = self.not_ready_streak


        # ─── Act: state-dependent side effects ───
        if readiness == ReadinessState.READY:
            if not lan.success:
                tlog(
                    "🟡",
                    "ROUTER",
                    "FLAKY",
                    primary="ICMP unreliable",
                    meta="WAN confirmed healthy"
                )

            # if public:
            self._reconcile_dns(public.ip)

        elif escalate and self.physical_recovery_available:
            if self._initiate_recovery():
                # Prevent recovery storms
                self.not_ready_streak = 0
 
        elif escalate:
            tlog(
                "🟡",
                "RECOVERY",
                "SUPPRESSED",
                primary="disabled by config",
                meta=f"down_count={self.not_ready_streak}"
            )


        # ─── Report: main network evaluation telemetry ───
        primary = []
        meta = []

        if readiness == ReadinessState.PROBING:
            primary.append("gate=HOLD")
            if (self.promotion_votes == 0):
                meta.append("awaiting confirmation")
            else:
                meta.append(
                    f"confirmations={self.promotion_votes}/"
                    f"{self.promotion_confirmations_required}"
                )
        elif readiness == ReadinessState.NOT_READY:
            primary.append("escalate=GO" if escalate else "escalate=HOLD")
            meta.append(
                f"down_count={self.not_ready_streak}/"
                f"{recovery_policy.max_consecutive_down_before_escalation}"
            )

        # Only log detailed NET_EVAL when not healthy
        if readiness is not ReadinessState.READY:
            tlog(
                READINESS_EMOJI[readiness],
                "NET_EVAL",
                readiness.name,
                primary=" ".join(primary),
                meta=" | ".join(meta) if meta else ""
            )

        return readiness
    