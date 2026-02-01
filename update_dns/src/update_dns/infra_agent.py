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
from .time_service import TimeService
from .cloudflare import CloudflareClient
from .bootstrap import RuntimeCapabilities
from .gsheets_service import GSheetsService
from .recovery_policy import recovery_policy
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip, CacheLookupResult, load_uptime
from .utils import ping_host, verify_wan_reachability, get_ip, doh_lookup, IPResolutionResult
#from .db import log_metrics


class NetworkState(Enum):
    """
    Canonical representation of overall network readiness.

    States are intentionally minimal and monotonic:
        INIT → DEGRADED → UP
        Any verified failure → DOWN
    """

    INIT = auto()
    UP = auto()
    DEGRADED = auto()
    DOWN = auto()
    ERROR = auto()

    def __str__(self) -> str:
        return self.name

NETWORK_EMOJI = {
    NetworkState.INIT:     "⚪",
    NetworkState.UP:       "💚",
    NetworkState.DEGRADED: "🟡",
    NetworkState.DOWN:     "🔴",
    NetworkState.ERROR:    "💣",
}

class NetworkHealthFSM:
    """
    Deterministic finite-state machine that powers reliable network health decisions.

    Single source of truth for whether the network is safe for side-effects (DNS updates,
    notifications, recovery actions). Designed from first principles for correctness
    over speed in noisy residential WAN environments.

    Key highlights:
    • Strict monotonic promotion (INIT/DOWN → DEGRADED → UP) — no flapping, no false optimism
    • Immediate fail-fast to DOWN on any verified failure — safety first
    • Promotion gating moved to external policy (allow_promotion)
      Simplifies FSM core; now defers final trust decision to secondary signals
      (e.g., consecutive stable public IPs) for cleaner separation of concerns
    • No internal counters or hysteresis in the FSM itself
      Keeps logic minimal, deterministic, and extremely easy to test/reason about
    • Pure, deterministic logic — zero timers, zero dependencies, fully testable

    Inspired by production patterns from Kubernetes operator/controller probes, but kept
    intentionally simple and lightweight.

    Every transition is reproducible from the same inputs. Built to be trusted.

    (This is one of those small components that quietly makes the whole system feel solid.)
    """

    def __init__(self):
        self.state: NetworkState = NetworkState.INIT

    def _enter_down(self) -> None:
        self.state = NetworkState.DOWN

    def transition(
            self, 
            wan_path_ok: bool, 
            allow_promotion: bool = True,
        ) -> NetworkState:
        """
        Network health is governed by a monotonic finite state machine (FSM):
        - Promotions proceed only INIT/DOWN → DEGRADED → UP; regressions never skip levels.
        - Any verified WAN failure triggers an immediate, fail-fast demotion to DOWN.
        - Promotion to UP is explicitly gated by external stability signals (IP consistency).
        - DEGRADED is a probationary hold state, never operational readiness.
        - All transitions are deterministic and evaluated once per control loop cycle.
        """
        if not wan_path_ok:
            self._enter_down()
            return self.state

        match self.state:
            case NetworkState.INIT | NetworkState.DOWN:
                self.state = NetworkState.DEGRADED

            case NetworkState.DEGRADED if allow_promotion:
                self.state = NetworkState.UP

            case _:
                pass  # UP stays UP

        return self.state


class NetworkControlAgent:
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
        - Emits a single authoritative NetworkState per control cycle
    """

    def __init__(self, capabilities: RuntimeCapabilities):
        """
        Initialize the NetworkControlAgent — the core autonomous network health monitor
        and self-healing orchestrator.

        Startup is designed to be resilient:
        - All failures during init are logged but do not halt execution
        - Starts conservatively in DEGRADED state (probationary)
        - No external priming/calls required at boot

        Initialization order reflects the agent's workflow:
        1. Pure dependencies (time, logging, external clients)
        2. Static configuration & policy thresholds
        3. State machine & initial health assessment
        4. Cross-cycle runtime state (memory between loops)
        """

        # ─── 1. Core dependencies & services ─── 
        self.time = TimeService()
        self.logger = get_logger("infra_agent")
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()
        self.gsheets_service.warmup()

        # ─── 2. Static configuration & policy thresholds ─── 
        self.router_ip = config.Hardware.ROUTER_IP
        self.max_cache_age_s = config.MAX_CACHE_AGE_S
        self.plug_ip = config.Hardware.PLUG_IP
        self.allow_physical_recovery = config.ALLOW_PHYSICAL_RECOVERY

        # Promotion policy
        self.confirmations_required_for_up = 2   # consecutive stable IPs needed

        # ─── 3. State machine (single source of truth for health) ─── 
        self.network_fsm = NetworkHealthFSM()
        # Starts in DEGRADED — probationary until 2 consecutive stable IPs confirmed
        # (self.confirmations_required_for_up = 2)
        # Cache seeds naturally during probation window (no priming needed)

        # ─── 4. Runtime / cross-cycle state (memory between control loops) ─── 
        # Previous state (for transition detection)
        self.previous_network_state: NetworkState = NetworkState.INIT

        # Failure escalation tracking
        self.consecutive_down_count: int = 0

        # IP stability gating (used only during INIT/DEGRADED probation)
        self.last_public_ip: Optional[str] = None
        self.ip_stability_count: int = 0   

        # Physical recovery guardrail
        self.last_recovery_time: float = 0.0  # far in the past → first recovery allowed immediately

        # Metrics
        self.uptime = load_uptime()

        # ─── Telemetry / epochs ───
        self.wan_epoch: int = 0


        self.physical_recovery_available = capabilities.physical_recovery_available
        self.logger.info(f"self.physical_recovery_available={self.physical_recovery_available}")


        ##################
        # For testing only
        ##################
        self.count = 0
        self.flag = True

    def _update_ip_stability(self, public_ip: Optional[str]) -> bool:
        """
        Tracks public IP continuity to serve as a conservative promotion gate.

        Used exclusively by the FSM to prevent premature UP transitions when
        secondary signals (public IP) are unstable.

        Semantics:
        • Any change/missing IP → reset stability counter
        • Identical consecutive IPs → increment counter
        • Returns True only after required consecutive matches

        Keeps the FSM clean by externalizing hysteresis — simple, deterministic,
        and focused on "has this IP been stable long enough?"
        """
        if not public_ip:
            self.ip_stability_count = 0
            self.last_public_ip = None
            return False

        if public_ip == self.last_public_ip:
            self.ip_stability_count += 1
        else:
            self.ip_stability_count = 1
            self.last_public_ip = public_ip

        return self.ip_stability_count >= self.confirmations_required_for_up

    def _on_network_down_transition(self):
        """
        Epochal reset hook triggered exactly once on entry to DOWN state.

        Ensures fresh evidence is required for recovery by:
        • Invalidating all prior promotion confidence
        • Clearing IP stability tracking
        • Forcing a clean slate after any verified failure

        This deliberate "forgetfulness" on failure is a safety feature:
        better to require new proof than risk acting on stale assumptions.
        """
        #self.wan_epoch += 1
        self.ip_stability_count = 0
        self.last_public_ip = None


    def _log_network_transition(
        self,
        from_state: NetworkState,
        to_state: NetworkState,
        promotion_allowed: Optional[bool] = None,
        ip_stability_count: Optional[int] = None,
    ):
        """
        Emit a single authoritative log line describing a NetworkState transition.
        """

        from_state = from_state or NetworkState.INIT
        arrow = f"{from_state.name} → {to_state.name}"
        meta = []

        if from_state == NetworkState.DEGRADED and to_state == NetworkState.UP:
            meta.append(
                f"confirmations={ip_stability_count}/{self.confirmations_required_for_up}"
            )

        tlog(
            NETWORK_EMOJI[to_state],
            "STATE",
            "CHANGE",
            primary=arrow,
            meta=" | ".join(meta) if meta else None,
        )

        # ─── Future Work ───
        # Send notification via 3rd party messaging app
        #  - Telegram's @BotFather API 
        #  - WhatsApp API??

    def _sync_dns_if_drifted(self, public_ip: str) -> None:
        """
        Reconciles Cloudflare DNS with the current public IP — only when safe.

        Called exclusively when NetworkState is UP (stable, verified WAN).
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
        dns_last_modified = \
            self.time.iso_to_local_string(result.get("modified_on"))
        
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

        # ─── Low-frequency audit log ───
        gsheets_ok, elapsed_ms = self.gsheets_service.update_status(
            ip_address=public_ip,
            current_time=None,
            dns_last_modified=dns_last_modified
        )

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

    def _trigger_physical_recovery(self) -> bool:
        """
        Orchestrate a policy-approved physical recovery attempt.

        Invoked only after escalation thresholds are met and recovery is explicitly
        allowed by policy. Acts as a clean boundary between failure detection
        (NetworkHealthFSM) and physical action.

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


    def update_network_health(self) -> NetworkState:
        """
        Execute one complete control cycle: observe network signals, assess health,
        decide on actions, perform side-effects (when safe), and report telemetry.

        This is the agent's main heartbeat — called repeatedly in the supervisor loop.

        Core workflow (strict phase separation for clarity & testability):
        1. Observe   → Collect raw, unfiltered reachability signals (LAN, WAN path, public IP)
        2. Assess    → Feed primary signal into NetworkHealthFSM (single source of truth)
        3. Decide    → Check escalation thresholds & promotion gates
        4. Act       → Trigger safe side-effects: DNS reconciliation, physical recovery
        5. Report    → Emit high-signal telemetry (detailed when degraded/down, minimal when UP)

        Key design principles:
        • FSM is the sole authority on health state — deterministic & monotonic
        • Side-effects are strictly gated by UP state + stability checks
        • Fail-fast & safe-by-default — no action without fresh evidence
        • Boring UP states are kept quiet; detailed logs only when building trust or failing

        Returns the updated NetworkState after this cycle.
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
        meta.append(f"tls=ok" if wan_path.success else "")

        tlog(
            "🟢" if wan_path.success else "🔴",
            "WAN_PATH",
            "UP" if wan_path.success else "DOWN",
            primary=f"dest={host}:{port}",
            meta=" | ".join(meta) if meta else ""
        )


        # ─── Policy: IP stability check (only when we have some confidence) ───
        allow_promotion = False
        public = None

        if (
            self.network_fsm.state is not NetworkState.DOWN
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

            # Determine whether promotion (DEGRADED → UP) is allowed
            if public.success and self.network_fsm.state == NetworkState.DEGRADED:
                allow_promotion = self._update_ip_stability(public.ip)

        else:
            tlog("🟡", "PUBLIC_IP", "SKIPPED")
        

        # ─── Assess: FSM transition (single source of truth) ───
        previous_state = self.previous_network_state
        network_state = self.network_fsm.transition(
            wan_path_ok=wan_path.success,
            allow_promotion = allow_promotion
        )

        # Transition telemetry (single line, high signal)
        if previous_state != network_state:
            self._log_network_transition(
                from_state=previous_state,
                to_state=network_state,
                promotion_allowed=allow_promotion,
                ip_stability_count=self.ip_stability_count,
            )    


        # ─── Decide + Act: edge-triggered actions ───
        if network_state == NetworkState.DOWN and self.previous_network_state != NetworkState.DOWN:
            self._on_network_down_transition()

        self.previous_network_state = network_state


        # ─── Decide: escalation check ───
        # Escalation counter increments only during DOWN
        if network_state == NetworkState.DOWN:
            self.consecutive_down_count += 1
        else:
            self.consecutive_down_count = 0

        escalate = (
            network_state == NetworkState.DOWN
            and self.consecutive_down_count >= recovery_policy.max_consecutive_down_before_escalation
        )
        failures_at_decision = self.consecutive_down_count


        # ─── Act: state-dependent side effects ───
        if network_state == NetworkState.UP:
            if not lan.success:
                tlog(
                    "🟡",
                    "ROUTER",
                    "FLAKY",
                    primary="ICMP unreliable",
                    meta="WAN confirmed healthy"
                )

            # if public:
            self._sync_dns_if_drifted(public.ip)

            # High-frequency uptime heartbeat
            _, dt_str = self.time.now_local()
            gsheets_ok, elapsed_ms = self.gsheets_service.update_status(
                ip_address=None,
                current_time=dt_str,
                dns_last_modified=None
            )
            if gsheets_ok:
                tlog("🟢", "GSHEET", "UPDATED", meta=f"rtt={elapsed_ms:.0f}ms")

        elif escalate and self.allow_physical_recovery:
            if self._trigger_physical_recovery():
                # Prevent recovery storms
                self.consecutive_down_count = 0
 
        elif escalate:
            tlog(
                "🟡",
                "RECOVERY",
                "SUPPRESSED",
                primary="disabled by config",
                meta=f"down_count={self.consecutive_down_count}"
            )


        # ─── Report: main network evaluation telemetry ───
        meta = []

        if network_state == NetworkState.DEGRADED:
            if (self.ip_stability_count == 0):
                meta.append("awaiting confirmation")
            else:
                meta.append(
                    f"confirmations={self.ip_stability_count}/"
                    f"{self.confirmations_required_for_up}"
                )
        elif network_state == NetworkState.DOWN:
            meta.append(
                f"down_count={self.consecutive_down_count}/"
                f"{recovery_policy.max_consecutive_down_before_escalation}"
            )
            meta.append(f"escalate={escalate}")

        # Only log detailed NET_EVAL when something is wrong or building confidence
        if network_state is not NetworkState.UP:
            tlog(
                NETWORK_EMOJI[network_state],
                "NET_EVAL",
                network_state.name,
                primary="gate=HOLD",
                meta=" | ".join(meta) if meta else ""
            )

        return network_state
    