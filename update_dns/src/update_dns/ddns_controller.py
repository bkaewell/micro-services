# ─── Standard library imports ───
import time
from enum import Enum, auto
from typing import Optional

# ─── Project imports ───
from .telemetry import tlog
from .recovery_policy import recovery_policy
from .cloudflare import CloudflareDNSProvider
from .recovery_controller import RecoveryController
from .readiness import ReadinessState, READINESS_EMOJI

from .utils import ping_host, verify_wan_reachability, get_ip, doh_lookup, IPResolutionResult  # test hook
from .cache import PersistentCache #load_cached_cloudflare_ip, store_cloudflare_ip, store_uptime
#from .db import log_metrics


class DDNSController:
    """
    Control-loop coordinator for WAN readiness and DDNS reconciliation.

    Responsibilities:
    • Observe LAN, WAN path, and public IP signals
    • Derive a single authoritative readiness verdict per cycle
    • Reconcile DNS only after stability is proven
    • Escalate recovery after sustained failure

    Design bias:
    • Conservative by default
    • Low-noise when healthy
    • Fail-fast, recover deliberately
    """
    # ─── Class Constants ───
    # consecutive stable IPs required for READY
    PROMOTION_CONFIRMATIONS_REQUIRED: int = 2

    def __init__(
            self,
            *,
            router_ip: str, 
            max_cache_age_s: str,
            readiness: ReadinessState,
            dns_provider: CloudflareDNSProvider, 
            recovery: RecoveryController,
            cache: PersistentCache,
        ):
        """
        Initialize the DDNS control loop.

        • Readiness FSM is the single source of truth
        • Recovery is policy-driven and externally gated
        • Startup assumes nothing about network health
        """

        # ─── Core Controle Plane (Single Source of Truth) ───
        self.readiness = readiness

        # ─── External Actuators ───
        self.dns_provider = dns_provider
        self.recovery = recovery

        # ─── Environment & Topology ─── 
        self.router_ip = router_ip

        # ─── Policy & Control Parameters ─── 
        self.max_cache_age_s = max_cache_age_s

        # ─── Promotion / Stability Tracking (Probation Logic) ───         
        self.last_public_ip: Optional[str] = None
        self.promotion_votes: int = 0   # consecutive confirmations
        
        # ─── Metrics & Long-Lived Counters ───
        self.cache = cache
        self.uptime = cache.load_uptime()
        self.loop = 1


        ##################
        # For testing only
        ##################
        self.count = 0
        self.flag = True

    def _record_ip_observation(self, public_ip: Optional[str]) -> bool:
        """
        Track consecutive public IP observations for promotion gating.

        • IP change or missing value resets confidence
        • Matching consecutive IPs build confidence
        • Returns True only after required confirmations

        Keeps hysteresis out of the FSM and easy to reason about.
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

        return self.promotion_votes >= DDNSController.PROMOTION_CONFIRMATIONS_REQUIRED

    def _log_readiness_change(
        self,
        prev: ReadinessState,
        current: ReadinessState,
        promotion_votes: Optional[int] = None,
    ):
        """
        Emit a single log line for a readiness state transition.
        """

        prev = prev or ReadinessState.INIT
        transition = f"{prev.name} → {current.name}"
        meta = []

        if prev == ReadinessState.PROBING and current == ReadinessState.READY:
            meta.append(
                f"confirmations={promotion_votes}/"
                f"{DDNSController.PROMOTION_CONFIRMATIONS_REQUIRED}"
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

    def _reconcile_dns_if_needed(self, public_ip: str) -> None:
        """
        Reconcile Cloudflare DNS with the current public IP.

        Invariants:
        • Called only when readiness is READY
        • Safe to call repeatedly (idempotent)
        • No mutation without authoritative confirmation

        Strategy:
        • L1: local cache (cheap no-op)
        • L2: DoH verification (truth without mutation)
        • L3: targeted update (only on confirmed drift)
        """

        # ─── L1 Local Cache (Cheap, fast no-op) ───
        # Only proceed to DoH if cache is absent, stale, or mismatched
        cache = self.cache.load_cloudflare_ip()
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
            tlog("🌐", "DDNS", "NO-OP", primary="cache=hit")
            return  # Fast no-op: we trust the cache = DNS = current IP

        # ─── L2 Authoritative DoH lookup ───
        doh = doh_lookup(self.dns_provider.dns_name)

        if doh.success and doh.ip == public_ip:
            tlog(
                "🟢",
                "DNS",
                "VERIFIED",
                primary=f"ip={doh.ip}",
                meta=f"rtt={doh.elapsed_ms:.0f}ms"
            )
            self.cache.store_cloudflare_ip(public_ip)
            tlog("🟢", "CACHE", "REFRESHED", primary=f"ttl={self.max_cache_age_s}s")
            tlog("🌐", "DDNS", "NO-OP", primary="doh=verified")
            return

        # ─── L3 Targeted update required (mutation) ───
        result, elapsed_ms = self.dns_provider.update_dns(public_ip)
        self.cache.store_cloudflare_ip(public_ip)

        meta=[]
        meta.append(f"rtt={elapsed_ms:.0f}ms")
        meta.append(f"desired={public_ip}")
        meta.append(f"ttl={self.dns_provider.ttl}s")
        tlog(
            "🟢",
            "CLOUDFLARE",
            "UPDATED",
            primary=f"dns={self.dns_provider.dns_name}",
            meta=" | ".join(meta)
        )
        tlog("🟢", "CACHE", "REFRESHED", primary=f"ttl={self.max_cache_age_s}s")
        tlog("🌐", "DDNS", "PUBLISHED", primary="reason=ip-mismatch")

    def _tick_uptime(self, readiness: ReadinessState) -> None:
        """
        Advance uptime counters for the current loop iteration.
        """
        self.uptime.total += 1

        if readiness == ReadinessState.READY:
            self.uptime.up += 1

        # Align with CACHE_MAX_AGE_S ~3600 seconds?

        # Persist periodically (best-effort)
        # if self.uptime.total % 50 == 0:
        #     self.cache.store_uptime(self.uptime)

        self.cache.store_uptime(self.uptime)

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


    def run_cycle(self) -> None:
        """
        Execute one autonomous control-loop cycle.

        Phases:
        1. Observe raw network signals
        2. Assess readiness (FSM)
        3. Emit an authoritative verdict
        4. Perform READY-only side effects (DDNS)
        5. Track failures + attempt recovery
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

        can_observe_public_ip = (
            wan.success
            and self.readiness.state != ReadinessState.NOT_READY
        )

        in_promotion_window = (
            self.readiness.state == ReadinessState.PROBING
        )

        if can_observe_public_ip:
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

            if public.success and in_promotion_window:
                allow_promotion = self._record_ip_observation(public.ip)

        else:
            tlog("🟡", "PUBLIC_IP", "SKIPPED")
        

        # ─── Assess: (FSM = single source of truth) ───
        prev = self.readiness.state

        self.readiness.advance(
            wan_path_ok=wan.success,
            allow_promotion = allow_promotion
        )

        current = self.readiness.state

        if prev != current:
            self._log_readiness_change(
                prev=prev,
                current=current,
                promotion_votes=self.promotion_votes,
            ) 

        # ─── Verdict: authoritative ───
        self.recovery.observe(current)
        verdict_primary = None
        verdict_meta = None

        if current == ReadinessState.PROBING:
            verdict_primary = "gate=HOLD"
            verdict_meta = (
                "awaiting confirmation"
                if self.promotion_votes == 0
                else (
                    f"confirmations={self.promotion_votes}/"
                    f"{DDNSController.PROMOTION_CONFIRMATIONS_REQUIRED}"
                )
            )

        elif current == ReadinessState.NOT_READY:
            verdict_primary = "observe-only"
            verdict_meta = (
                f"down_count={self.recovery.not_ready_streak}/"
                f"{recovery_policy.max_consecutive_down_before_escalation}"
            )

        tlog(
            READINESS_EMOJI[current],
            "VERDICT",
            current.name,
            primary=verdict_primary,
            meta=verdict_meta,
        )

        entering_not_ready = (
            prev != ReadinessState.NOT_READY
            and current == ReadinessState.NOT_READY
        )

        if entering_not_ready:
            # This guarantees that recovery always requires fresh evidence
            # (no promotion carryover, no stale IP stability).
            self.promotion_votes = 0
            self.last_public_ip = None


        # ─── Act: READY-only side effects ───
        if current == ReadinessState.READY:
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
        else:
            self.recovery.maybe_recover()

        self._tick_uptime(current)

        elapsed_ms = (time.monotonic() - start) * 1000
        tlog(
            "🔁",
            "LOOP",
            "COMPLETE",
            meta=f"loop={elapsed_ms:.0f}ms | uptime={self.uptime}"
        )

        self.loop += 1
