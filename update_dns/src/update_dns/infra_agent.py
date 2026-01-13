# --- Standard library imports ---
import time
from enum import Enum, auto
from typing import Optional

# --- Third-party imports ---
import requests

# --- Project imports ---
from .config import Config
from .telemetry import tlog
from .logger import get_logger
from .time_service import TimeService
from .cloudflare import CloudflareClient
from .gsheets_service import GSheetsService
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip
from .utils import ping_host, verify_wan_reachability, get_ip, doh_lookup, IPResolutionResult
#from .db import log_metrics


class NetworkState(Enum):
    HEALTHY = auto()
    DEGRADED = auto()
    DOWN = auto()
    ERROR = auto()
    UNKNOWN = auto()

    @property
    def label(self) -> str:
        return {
            NetworkState.HEALTHY: "HEALTHY",
            NetworkState.DEGRADED: "DEGRADED",
            NetworkState.DOWN: "DOWN",
            NetworkState.ERROR: "ERROR",
            NetworkState.UNKNOWN: "UNKNOWN",
        }[self]

class WanState(Enum):
    """
    Canonical WAN health states with monotonic promotion semantics.

    DOWN:
        No trustworthy evidence of external reachability.
        This state represents *absence of confidence*, not merely a transient failure.
        Any ambiguity or signal disagreement collapses the system into DOWN.

    DEGRADED:
        Partial or emerging evidence of WAN viability.
        External reachability may exist, but stability and continuity
        have not yet been established.
        DEGRADED is a probationary state and MUST NOT be treated as operationally safe.

    UP:
        Sustained, corroborated evidence of WAN health.
        Entry into UP requires consecutive good observations and explicit promotion gating.
        UP implies the system may perform side-effecting network actions.
    """
    UP = auto()
    DEGRADED = auto()
    DOWN = auto()

WAN_HEALTH_EMOJI = {
    WanState.UP: "🟢",
    WanState.DEGRADED: "🟡",
    WanState.DOWN: "🔴",
}

class WanFSM:
    """
    Deterministic finite-state machine that models WAN health confidence
    over time.

    This component is intentionally narrow in scope: it converts raw,
    per-cycle network observations into a stable, policy-friendly WAN
    health signal. It smooths transient noise, enforces monotonic promotion
    (DOWN → DEGRADED → UP), and collapses trust immediately on verified
    failure.

    Design principles:
        - Signal > action: classification only, no recovery side effects
        - Deterministic and testable: same inputs always yield the same state
        - Noise-tolerant: requires consecutive good observations to promote
        - Fail-fast: any true failure resets confidence immediately

    Explicitly out of scope:
        - Recovery or escalation logic
        - Timers, sleeps, or wall-clock dependencies
        - External side effects or I/O
    """

    def __init__(self, min_degraded_confirmations: int = 2):
        """
        Initialize the WAN health state machine.

        Args:
            min_degraded_confirmations:
                Number of consecutive, clean observations required to
                promote WAN health from DEGRADED to UP. This encodes
                confidence-building rather than instantaneous trust.
        """
        self.state: WanState = WanState.DOWN
        self.min_degraded_confirmations = min_degraded_confirmations
        self.good_observation_count = 0

    def _enter_down(self) -> None:
        """
        Force a transition to DOWN and discard all accumulated confidence.

        This method represents a hard trust reset and is invoked whenever
        the WAN is observed to be definitively unhealthy. Recovery and
        remediation decisions are handled by higher-level policy layers.
        """
        self.state = WanState.DOWN
        self.good_observation_count = 0

    def transition(
        self,
        #lan_ok: bool,
        wan_path_ok: bool,
        public_ok: bool,
        allow_promotion: bool = True,
    ) -> WanState:
        """
        Advance the WAN health state based on the strongest available signals.

        This method evaluates observations in order of trustworthiness and
        updates internal confidence accordingly. Promotion is monotonic and
        gated by both signal quality and explicit policy approval.

        Signal model:
            - WAN path reachability: strong
            - Public IP resolution: strongest
            - LAN reachability: intentionally excluded to avoid false negatives

        State transitions:
            - Any verified failure → DOWN (confidence reset)
            - First clean observation → DEGRADED
            - N consecutive clean observations → UP (if promotion allowed)

        Args:
            wan_path_ok:
                Whether external WAN reachability succeeded.
            public_ok:
                Whether a public IP was successfully observed.
            allow_promotion:
                External policy gate used to delay DEGRADED → UP
                (e.g., IP stability requirements).

        Returns:
            The updated WanState after applying this observation.
        """

        # Strong WAN evidence overrides LAN probe noise
        if wan_path_ok and public_ok:
            self.good_observation_count += 1

            if self.state == WanState.DOWN:
                self.state = WanState.DEGRADED

            elif (
                self.state == WanState.DEGRADED
                and self.good_observation_count >= self.min_degraded_confirmations
                and allow_promotion
            ):
                self.state = WanState.UP

            return self.state
    
        # True failure paths
        self._enter_down()
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

    def __init__(self):
        """
        Initialize the NetworkControlAgent runtime, policies, and observation state.

        The agent is designed to be resilient at startup: initialization failures
        are logged but do not prevent execution.
        """

        # --- Core services (pure dependencies) --- 
        self.time = TimeService()
        self.cloudflare_client = CloudflareClient()
        self.gsheets_service = GSheetsService()
        # Future work - add notifications via Telegram API
        self.logger = get_logger("infra_agent")

        # --- Static configuration ---
        self.router_ip = Config.Hardware.ROUTER_IP
        self.allow_physical_recovery = Config.ALLOW_PHYSICAL_RECOVERY

        # --- WAN promotion policy (health → trust) ---
        self.WAN_PROMOTION_CYCLES = 2   # DEGRADED → UP requires N clean observations
        self.MAX_CONSECUTIVE_FAILS = 4  # Escalation threshold

        self.wan_fsm = WanFSM(
            min_degraded_confirmations=self.WAN_PROMOTION_CYCLES
        )

        # --- WAN observation state (cross-cycle memory) ---
        self.last_wan_state: Optional[WanState] = None
        self.consecutive_fails: int = 0

        # IP stability (used ONLY during WAN DEGRADED)
        self.last_public_ip: Optional[str] = None
        self.ip_stability_count: int = 0        

        # --- Telemetry / epochs ---
        self.wan_epoch: int = 0

        # --- startup priming ---
        self._prime_dns_cache()

        ##################
        # For testing only
        ##################
        self.count = 0
        self.flag = True

    def _prime_dns_cache(self) -> None:
        """
        Opportunistically seed the local DNS cache using authoritative DNS-over-HTTPS (DoH).

        This function establishes an initial reference point for future DNS drift detection
        without asserting correctness or availability guarantees.

        Design principles:
        - Best-effort only: failures are explicitly tolerated
        - Non-blocking: never delays or aborts agent startup
        - Non-authoritative: primes signal state, not system truth

        A successful prime reduces unnecessary external lookups during early runtime.
        An unsuccessful prime degrades gracefully and defers correctness to later reconciliation.
        """
        try:

            doh = doh_lookup(self.cloudflare_client.dns_name)

            if doh.success and doh.ip:
                store_cloudflare_ip(doh.ip)
                self.logger.info(
                    "DNS cache primed via DoH | "
                    f"ip={doh.ip} rtt={doh.elapsed_ms:.1f}ms"
                )
            else:
                store_cloudflare_ip("__INIT__")
                self.logger.warning(
                    "DNS cache not primed | "
                    f"success={doh.success} "
                    f"rtt={doh.elapsed_ms:.1f}ms"
                )
    
        except Exception as e:
            store_cloudflare_ip("")
            self.logger.error(
                f"DNS cache priming failed | error={type(e).__name__}: {e}"
            )

    def _update_ip_stability(self, public_ip: Optional[str]) -> bool:
        """
        Evaluate public IP continuity across consecutive observation cycles.

        This function tracks *stability*, not correctness, and is used exclusively
        as a promotion guard when transitioning WAN state from DEGRADED → UP.

        Semantics:
        - Any missing or invalid IP immediately resets stability confidence
        - Stability is defined as repeated identical observations over time
        - This function has no side effects beyond internal counters

        Returns:
            True if the public IP has remained stable for the required
            promotion window; False otherwise.
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

        return self.ip_stability_count >= self.WAN_PROMOTION_CYCLES

    def _on_wan_down_transition(self):
        """
        Execute epochal reset logic on WAN DOWN transitions.

        This hook is invoked exactly once per DOWN entry and is responsible
        for invalidating all accumulated promotion confidence.

        Actions:
        - Advance the WAN epoch to invalidate stale observations
        - Clear IP stability tracking
        - Reset any DEGRADED/UP promotion state

        This ensures that recovery always requires fresh, post-failure evidence.
        """
        self.wan_epoch += 1
        #self.ip_good_observation_count = 0
        self.ip_stability_count = 0
        self.last_public_ip = None

    def _sync_dns_if_drifted(self, public_ip: str) -> None:
        """
        Reconcile authoritative DNS state with the currently observed public IP.

        This method enforces eventual consistency between runtime network identity
        and provider-managed DNS records using a strictly layered strategy:

            L1: Local cache
                Fast, zero-cost short-circuit for known-good state

            L2: Authoritative DoH verification
                External truth check without mutation

            L3: Provider mutation
                Executed only when drift is positively identified

        Safety and correctness guarantees:
        - Idempotent: repeated calls converge without side effects
        - Mutation-safe: provider updates occur only after authoritative mismatch
        - Stability-gated: MUST be called only when WAN state is confirmed UP

        This function represents the sole mutation path for DNS correction.
        """

        # --- L1 Cache (Cheap, local, fast no-op) ---
        cache = load_cached_cloudflare_ip()
        cache_match = cache.hit and cache.ip == public_ip

        tlog(
            "🟢" if cache_match else "🟡",
            "CACHE",
            "HIT" if cache_match else "MISS",
            primary=f"ip={cache.ip}",
            meta=f"rtt={cache.elapsed_ms:.1f}ms"
        )

        if cache_match:
            return  # Fast no-op

        # --- L2 DoH (Authoritative DNS, external truth) ---
        doh = doh_lookup(self.cloudflare_client.dns_name)

        if doh.success and doh.ip == public_ip:
            tlog(
                "🟢",
                "DNS",
                "OK",
                primary=f"ip={doh.ip}",
                meta=f"rtt={doh.elapsed_ms:.1f}ms"
            )
            store_cloudflare_ip(public_ip)   # Refresh cache
            return

        # --- Mutation required ---
        result = self.cloudflare_client.update_dns(public_ip)
        store_cloudflare_ip(public_ip)
        dns_last_modified = \
            self.time.iso_to_local_string(result.get("modified_on"))
        tlog(
            "🟢",
            "DNS",
            "UPDATED",
            primary="provider=Cloudflare",
            meta=f"{doh.ip} → {public_ip} | modified={dns_last_modified}"
        )

        # --- Low-frequency audit log ---
        gsheets_ok = self.gsheets_service.update_status(
                ip_address=public_ip,
                current_time=None,
                dns_last_modified=dns_last_modified
        )
        if gsheets_ok:
            tlog("🟢", "GSHEET", "OK", primary="audit dns update")

    def _power_cycle_edge(self) -> bool:
        """
        Execute a hard, out-of-band recovery by power-cycling the network edge device.

        This method represents the lowest-level physical remediation primitive available
        to the system. It performs a deterministic OFF → delay → ON sequence via a
        smart power relay and makes no attempt to assess network health, validate outcomes,
        or infer recovery success beyond command execution.

        Architectural boundaries:
        - This function is deliberately policy-agnostic
        - It performs no retries, backoff, or escalation
        - It MUST NOT be invoked except by higher-level recovery orchestration

        Any decision about *when* or *whether* to invoke this action is owned entirely
        by the WAN finite-state machine and its escalation policy.

        Returns:
            True if the relay command sequence completed successfully end-to-end.
            False if communication with the smart plug failed or an unexpected
            execution error occurred.
        """

        plug_ip = Config.Hardware.PLUG_IP
        reboot_delay = Config.Hardware.REBOOT_DELAY

        try:
            # Power OFF
            off = requests.get(
                f"http://{plug_ip}/relay/0?turn=off", 
                timeout=Config.API_TIMEOUT
            )
            off.raise_for_status()
            self.logger.debug("Smart plug powered OFF")

            time.sleep(reboot_delay)

            # Power ON
            on = requests.get(
                f"http://{plug_ip}/relay/0?turn=on", 
                timeout=Config.API_TIMEOUT
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
        Execute a policy-authorized physical WAN recovery action.

        This method acts as the orchestration boundary between abstract failure
        classification (WAN FSM) and concrete physical remediation. It is invoked
        only after escalation thresholds have been met and recovery has been deemed
        permissible by policy.

        Responsibilities:
        - Emit operator-grade telemetry before and after recovery
        - Execute exactly one physical recovery attempt
        - Provide a boolean execution outcome to the control loop

        Non-responsibilities:
        - No health re-evaluation
        - No retry logic
        - No suppression or rate limiting (handled upstream)

        Returns:
            True if the recovery command sequence executed successfully.
            False otherwise.
        """

        plug_ip = Config.Hardware.PLUG_IP
        sleep = Config.Hardware.REBOOT_DELAY

        tlog(
            "🔴", 
            "RECOVERY", 
            "TRIGGER", 
            primary="power-cycle edge device",
            meta=f"sleep={sleep}s"
        )
    
        plug_ok = ping_host(plug_ip)

        tlog(
            "🟡",
            "EDGE",
            "COMMAND",
            primary="plug-relay toggle",
            meta=f"plug_ip={plug_ip}"
        )

        success = self._power_cycle_edge()

        plug_ok_after = ping_host(plug_ip)

        tlog(
            "🟢" if success else "🔴",
            "RECOVERY",
            "OK" if success else "FAIL",
            primary="recovery attempt complete",
            meta=f"plug_pre_toggle={plug_ok} | plug_post_toggle={plug_ok_after}"
        )

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
                success=True,
            )
        
        return public

    #********************************
    #********************************
    #********************************
    #********************************
    #********************************


    def run_control_cycle(self) -> NetworkState:
        """
        Execute one deterministic network control-loop iteration.

        This method implements a closed-loop control system with strict phase
        separation and single-source-of-truth semantics:

            Observe  →  Assess  →  Decide  →  Act  →  Report

        Phase responsibilities:
        - Observe:
            Collect raw, fallible signals (LAN, WAN path, public IP) with no inference.
        - Assess:
            Delegate all WAN health classification to the WanFSM.
            The FSM output is treated as ground truth.
        - Decide:
            Apply policy thresholds and escalation rules without reinterpreting health.
        - Act:
            Perform side effects (DNS mutation, physical recovery) only when authorized.
        - Report:
            Emit structured telemetry for operators and external audit systems.

        Core invariants:
        - WanFSM is the sole authority on WAN health state
        - Side effects are gated on explicit, stable health states
        - Physical recovery is rate-limited via consecutive failure accounting
        - UP state implies a verified, stable public IP

        Returns:
            NetworkState reflecting the externally visible health of the system
            after this control cycle completes.
        """

        # --- Heartbeat (process liveness only) ---
        _, dt_str = self.time.now_local()
        tlog("💚", "HEARTBEAT", "OK")

        # ---OBSERVE ---
        # --- LAN ---
        lan_ok = ping_host(self.router_ip)
        tlog(
            "🟢" if lan_ok else "🔴",
            "ROUTER",
            "UP" if lan_ok else "DOWN",
            primary=f"ip={self.router_ip}"
        )

        # --- WAN path ---
        wan_path_ok = verify_wan_reachability()
        tlog(
            "🟢" if wan_path_ok else "🔴",
            "WAN",
            "PATH",
            primary="OK" if wan_path_ok else "FAIL"
        )

        # --- Public IP ---
        public = get_ip()

        #********************************
        #********************************
        #********************************
        #public = self._override_public_ip_for_test(public)  
        #self.count += 1
        #********************************
        #********************************
        #********************************

        tlog(
            "🟢" if public.success else "🔴",
            "PUBLIC IP",
            "OK" if public.success else "FAIL",
            primary=f"ip={public.ip}",
            meta=f"rtt={public.elapsed_ms:.1f}ms | attempts={public.attempts}"
        )

        # --- ASSESS (FSM owns health) ---

        # Determine whether promotion (DEGRADED → UP) is allowed
        allow_promotion = True

        if self.wan_fsm.state == WanState.DEGRADED:
            allow_promotion = self._update_ip_stability(public.ip)

        # WanFSM is the sole authority for WAN health
        # Treat its output as ground truth
        wan_state = self.wan_fsm.transition(
            #lan_ok=lan_ok,
            wan_path_ok=wan_path_ok,
            public_ok=public.success,
            allow_promotion = allow_promotion,
        )

        # Detect first transition into DOWN (telemetry hook)
        if wan_state == WanState.DOWN and self.last_wan_state != WanState.DOWN:
            self._on_wan_down_transition()

        self.last_wan_state = wan_state

        # --- DECIDE (policy & escalation) ---
        if wan_state == WanState.DOWN:
            self.consecutive_fails += 1
        else:
            self.consecutive_fails = 0

        escalate = (
            wan_state == WanState.DOWN
            and self.consecutive_fails >= self.MAX_CONSECUTIVE_FAILS
        )

        # --- REPORT (telemetry) ---
        meta = []
        if wan_state == WanState.UP:
            meta.append(f"confidence={self.wan_fsm.good_observation_count} loops")
        elif wan_state == WanState.DEGRADED:
            meta.append(
                f"confidence={self.wan_fsm.good_observation_count}/"
                f"{self.wan_fsm.min_degraded_confirmations} observations"
            )
        elif wan_state == WanState.DOWN:
            meta.append(f"failures={self.consecutive_fails}/{self.MAX_CONSECUTIVE_FAILS}")
            meta.append(f"escalate={escalate}")

        tlog(
            WAN_HEALTH_EMOJI[wan_state],
            "WAN",
            "STATE",
            primary=wan_state.name,
            meta=" | ".join(meta)
        )

        # --- ACT (side effects) ---
        # NOTE:
        # LAN/router reachability is a weak, noisy signal and must never
        # override WAN FSM health once public IP and WAN path are confirmed.
        if not lan_ok and wan_state == WanState.UP:
            tlog(
                "🟡",
                "LAN",
                "FLAKY",
                primary="router ICMP unreliable",
                meta="WAN confirmed healthy"
            )

        if wan_state == WanState.UP:
            assert public.success and public.ip, "UP WAN requires valid public IP"

            self._sync_dns_if_drifted(public.ip)

            # High-frequency uptime heartbeat
            if self.gsheets_service.update_status(
                ip_address=None,
                current_time=dt_str,
                dns_last_modified=None
            ):
                tlog("🟢", "GSHEET", "OK")

            return NetworkState.HEALTHY

        if wan_state == WanState.DEGRADED:
            return NetworkState.DEGRADED

        # --- WAN DOWN ---
        if escalate and self.allow_physical_recovery:
            recovery_ok = self._trigger_physical_recovery()

            if recovery_ok:
                # Successful recovery prevents rapid re-trigger loops
                self.consecutive_fails = 0
 
        elif escalate:
            tlog(
                "🟡",
                "RECOVERY",
                "SUPPRESSED",
                primary="physical recovery disabled",
                meta="failure threshold reached"
            )

        return NetworkState.DOWN

