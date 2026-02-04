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
from .bootstrap import EnvCapabilities
from .cloudflare import CloudflareClient
from .recovery_policy import recovery_policy
from .recovery_controller import RecoveryController
from .readiness import ReadinessState, READINESS_EMOJI, ReadinessController

from .utils import ping_host, verify_wan_reachability, get_ip, doh_lookup, IPResolutionResult
from .cache import load_cached_cloudflare_ip, store_cloudflare_ip, CacheLookupResult, load_uptime, store_uptime
#from .db import log_metrics


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

    def __init__(
            self, 
            readiness: ReadinessState, 
            recovery: RecoveryController
        ):
        """
        Core autonomous network controller.

        Design principles:
        - Conservative startup (probationary, no assumptions)
        - Single source of truth for readiness (FSM)
        - Edge-triggered recovery with hard guardrails
        """

        # ─── Readiness Controller (single source of truth) ─── 
        self.readiness = readiness
        self.prev_readiness: ReadinessState = ReadinessState.INIT


        self.recovery = recovery

        # ─── Observability & External Interfaces ─── 
        self.logger = get_logger("ddns_controller")
        self.cloudflare_client = CloudflareClient()

        # ─── Environment & Hardware Topology ─── 
        self.router_ip = config.Hardware.ROUTER_IP

        # ─── Policy & Control Parameters ─── 
        self.max_cache_age_s = config.MAX_CACHE_AGE_S
        self.promotion_confirmations_required = 2   # consecutive stable IPs required for READY

        # ─── Promotion / Stability Tracking (Probation Logic) ───         
        self.last_public_ip: Optional[str] = None
        self.promotion_votes: int = 0   # consecutive confirmations
        
        # ─── Metrics & Long-Lived Counters ───
        self.uptime = load_uptime()
        self.loop = 1


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

    def _reconcile_dns_if_needed(self, public_ip: str) -> None:
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
        ddns_decision  = None
        ddns_reason = None

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
            ddns_decision = "NO-OP"
            ddns_reason = "cache=hit"
            tlog("🌐", "DDNS", ddns_decision, primary=ddns_reason)
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
            ddns_decision = "NO-OP"
            ddns_reason = "doh=verified"
            tlog("🌐", "DDNS", ddns_decision, primary=ddns_reason)
            return

        # ─── L3 Mutation required ───
        result, elapsed_ms = self.cloudflare_client.update_dns(public_ip)
        store_cloudflare_ip(public_ip)       # Safe: we just wrote it

        ddns_decision = "UPDATED"
        ddns_reason = "reason=ip-mismatch"
        meta=[]
        meta.append(f"rtt={elapsed_ms:.0f}ms")
        meta.append(f"desired={public_ip}")
        meta.append(f"ttl={self.cloudflare_client.ttl}s")
        tlog(
            "🟢",
            "CLOUDFLARE",
            "UPDATED",
            primary=f"dns={self.cloudflare_client.dns_name}",
            meta=" | ".join(meta)
        )
        tlog("🟢", "CACHE", "REFRESHED", primary=f"ttl={self.max_cache_age_s}s")
        tlog("🌐", "DDNS", ddns_decision, primary=ddns_reason)


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


    def run_cycle(self) -> ReadinessState:
        """
        One autonomous control cycle.

        Phases:
        1. Observe raw signals
        2. Assess readiness (FSM)
        3. Emit verdict
        4. Act on READY (DDNS)
        5. Observe + attempt recovery
        6. Loop telemetry
        """
        start = time.monotonic()
        heartbeat = heartbeat = time.strftime("%a %b %d %Y")
        tlog("🔁", "LOOP", "START", primary=heartbeat, meta=f"loop={self.loop}")

        # ─── Observe: raw signals only ───
        # LAN (weak signal; informational only)
        lan = ping_host(self.router_ip)
        tlog(
            "🟢" if lan.success else "🔴",
            "ROUTER",
            "UP" if lan.success else "DOWN",
            primary=f"ip={self.router_ip}",
            meta=f"rtt={lan.elapsed_ms:.0f}ms"
        )

        # WAN path reachability (strong signal; feeds Network Health FSM)
        wan = verify_wan_reachability(host="1.1.1.1", port=443)
        tlog(
            "🟢" if wan.success else "🔴",
            "WAN_PATH",
            "UP" if wan.success else "DOWN",
            primary="dest=1.1.1.1:443",
            meta=f"rtt={wan.elapsed_ms:.0f}ms" + (" | tls=ok" if wan.success else ""),
        )

        public = None
        allow_promotion = False

        if wan.success and self.readiness.state != ReadinessState.NOT_READY:
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

            # Promotion confidence accrual (PROBING only)
            if public.success and self.readiness.state == ReadinessState.PROBING:
                allow_promotion = self._record_ip_observation(public.ip)

        else:
            tlog("🟡", "PUBLIC_IP", "SKIPPED")
        

        # ─── Assess: (FSM = single source of truth) ───
        prev = self.prev_readiness
        readiness = self.readiness.advance(
            wan_path_ok=wan.success,
            allow_promotion = allow_promotion
        )

        if prev != readiness:
            self._log_readiness_change(
                prev=prev,
                current=readiness,
                promotion_votes=self.promotion_votes,
            ) 

        # ─── Verdict: authoritative ───
        verdict_primary = None
        verdict_meta = None

        if readiness == ReadinessState.PROBING:
            verdict_primary = "gate=HOLD"
            verdict_meta = (
                "awaiting confirmation"
                if self.promotion_votes == 0
                else (
                    f"confirmations={self.promotion_votes}/"
                    f"{self.promotion_confirmations_required}"
                )
            )

        elif readiness == ReadinessState.NOT_READY:
            verdict_primary = "observe-only"
            verdict_meta = (
                f"down_count={self.not_ready_streak}/"
                f"{recovery_policy.max_consecutive_down_before_escalation}"
            )

        tlog(
            READINESS_EMOJI[readiness],
            "VERDICT",
            readiness.name,
            primary=verdict_primary,
            meta=verdict_meta,
        )

        entering_not_ready = (
            self.prev_readiness != ReadinessState.NOT_READY
            and readiness == ReadinessState.NOT_READY
        )

        if entering_not_ready:
            # This guarantees that recovery always requires fresh evidence
            # (no promotion carryover, no stale IP stability).
            self.promotion_votes = 0
            self.last_public_ip = None

        self.prev_readiness = readiness


        # ─── Decide: escalation tracking ───
        if readiness == ReadinessState.NOT_READY:
            self.not_ready_streak += 1
        else:
            self.not_ready_streak = 0

        escalate = (
            readiness == ReadinessState.NOT_READY
            and self.not_ready_streak >= recovery_policy.max_consecutive_down_before_escalation
        )
        #failures_at_decision = self.not_ready_streak




        # ─── Act: READY-only side effects ───
        if readiness == ReadinessState.READY:
            if not lan.success:
                tlog(
                    "🟡",
                    "ROUTER",
                    "FLAKY",
                    primary="ICMP unreliable",
                    meta="WAN confirmed healthy"
                )

            # DDNS reconciliation (safe to act)
            # if public and public.success:
            self._reconcile_dns_if_needed(public.ip)




        self.recovery.observe(readiness)
        self.recovery.maybe_recover()




        #elif escalate and self.physical_recovery_available:
        if escalate and self.physical_recovery_available:
            if self._initiate_recovery():
                # Prevent recovery storms
                self.not_ready_streak = 0
 
                # tlog(
                #     "🚨",
                #     "RECOVERY",
                #     "INITIATED",
                #     primary="physical intervention"
                # )

        #elif escalate:
        if escalate:
            tlog(
                "🟡",
                "RECOVERY",
                "SUPPRESSED",
                primary="disabled by config",
                meta=f"down_count={self.not_ready_streak}"
            )


        # ─── Uptime Cycle Counting ───
        self.uptime.total += 1
        if readiness == ReadinessState.READY:
            self.uptime.up += 1

        # Optional: save every 50 measurements (low I/O)
        #if self.uptime.total % 50 == 0:
        # Align with CACHE_MAX_AGE_S ~3600 seconds?
        store_uptime(self.uptime)

        elapsed_ms = (time.monotonic() - start) * 1000
        tlog(
            "🔁",
            "LOOP",
            "COMPLETE",
            meta=f"loop={elapsed_ms:.0f}ms | uptime={self.uptime}"
        )

        self.loop += 1
        return readiness
    