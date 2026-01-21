## Time Budget & Tuning Guide (Rev 0)

These parameters form the agent's **adaptive heartbeat** — balancing quick recovery during outages with minimal external I/O in steady state.  

The system is designed around Cloudflare's 60-second TTL:  
- We never poll meaningfully faster than TTL (avoids false positives)  
- We aggressively recover when unhealthy  
- We become very quiet and thrifty when healthy  

| Parameter                        | Default     | Purpose & Effect                                                                 | Tuning Guidance                                                                 | Interdependencies & Engineering Notes                                                                 |
|----------------------------------|-------------|----------------------------------------------------------------------------------|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| `CYCLE_INTERVAL_S`               | 60s         | Base cycle length in steady state (UP)                                          | 60–120s<br>Should be ≥ TTL (60s) to avoid false drift detection              | Core heartbeat. Too fast → unnecessary DoH/API calls. Too slow → delayed recovery. Chosen just above TTL for safety margin. Works as a baseline for state-scaled intervals.|
| `FAST_POLL_SCALAR`               | 0.5         | Multiplier during DOWN/DEGRADED → ~2× faster polling (~30s cycles)           | Lower = more aggressive recovery                                     | Enables rapid detection & recovery. Combined with jitter, keeps API load reasonable even when "fast". |
| `SLOW_POLL_SCALAR`               | 2.0         | Multiplier in steady UP → ~2× slower polling (~120s cycles)                    | Higher = more I/O savings                                            | The biggest win for long-term API thriftiness. Turns agent into a very quiet observer when healthy. |
| `POLLING_JITTER_S`               | 10s         | Adds a random offset to every interval                                          | Smaller = tighter pattern; larger = more human-like                  | Clever anti-rate-limit defense. Makes calls appear random/natural even with adaptive intervals. |
| `MAX_CACHE_AGE_S`                | 600s (10 min)  | Max age before cached DNS IP is considered stale → forces DoH re-verification | 300–900s (5–15 min)<br>~5× TTL is safe sweet spot                               | Saves expensive DoH calls in steady state (~5–8 cycles between checks). Forces refresh during long offline → catches external changes. |
| `CLOUDFLARE_MIN_TTL_S`           | 60s         | Cloudflare's minimum TTL for unproxied records (hard limit)                     | Fixed (non-tunable)                                                             | Foundation of all timing decisions. Cycle interval ≥ TTL prevents chasing false drift. |
| `API_TIMEOUT_S`                  | 8s          | Timeout for all external HTTP/DoH calls                                          | 5–12 s                                                                          | Safety net. Too low → false negatives; too high → hangs cycle. 8s is proven balanced for residential networks. |
| `REBOOT_DELAY_S`                 | 30s         | Delay between power-off and power-on during physical recovery                   | 15–60s<br>Depends on device boot time                                          | Hardware protection. Long enough for capacitors to discharge, short enough for quick recovery. |
| `RECOVERY_COOLDOWN_S`            | 1800s (30 min)  | Minimum time between physical recovery attempts                                 | 900–3600s (15–60 min)<br>Higher = more hardware safety                         | Prevents relay thrashing / power supply stress. 30 min is conservative for home hardware longevity. |

### Quick Tuning Philosophy

- **Healthy (UP)** → very slow + jittered polling + long cache life → **extremely low I/O** (goal: near-zero unnecessary API calls)
- **Unhealthy** → fast polling → **quick detection & recovery**
- **Safety everywhere** → TTL-aware intervals, cache freshness checks, cooldowns, timeouts
- **Human-like behavior** → jitter prevents pattern-based rate limiting

These values are deliberately conservative defaults — tune aggressively only if you understand your hardware, ISP stability, and Cloudflare usage patterns.

Happy tuning!





# TUNING.md – Time Budget & Parameter Guide (Rev 1)

This file explains the most important timing and behavioral knobs in the agent.  
The system is deliberately biased toward **safety**, **low I/O in steady state**, and **fast recovery when unhealthy**.

## Summary Table – Knobs, Beliefs, Derived Values & Assumptions

| Category                  | Parameter / Derived Value                        | Default / Formula                               | Purpose & Effect                                                                 | Tuning Guidance / Limits                                   | Engineering Notes / Why It Exists                                                                 |
|---------------------------|--------------------------------------------------|-------------------------------------------------|----------------------------------------------------------------------------------|------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| **Config – Core Knobs**   | `CYCLE_INTERVAL_S`                               | 60–65 s                                         | Baseline control cycle length (UP state)                                         | 60–120 s (≥ TTL)                                           | Foundation of all timing. Too fast → API spam. Too slow → delayed recovery. |
|                           | `POLLING_JITTER_S`                               | 5–10 s                                          | ± random offset on every cycle                                                   | 3–15 s                                                     | Prevents detectable periodic patterns → avoids rate limiting. Human-like behavior. |
|                           | `FAST_POLL_SCALAR`                               | 0.5                                             | Multiplier during DOWN/DEGRADED (~2× faster)                                     | 0.3–0.8                                                    | Aggressive recovery when unhealthy. |
|                           | `SLOW_POLL_SCALAR`                               | 2.0                                             | Multiplier in steady UP (~2× slower)                                             | 1.5–3.0                                                    | Biggest win for long-term API/DoH savings. |
|                           | `MAX_CACHE_AGE_S`                                | 600 s (10 min)                                  | Max cache age before forcing DoH re-verification                                 | 300–900 s (~5–15× TTL)                                     | Balances cheap local reads vs authoritative truth. Chosen to cover ~5 slow cycles. |
|                           | `API_TIMEOUT_S`                                  | 8 s                                             | Timeout for all external HTTP/DoH calls                                          | 5–12 s                                                     | Safety net against hangs / slow endpoints. |
| **RecoveryPolicy – Safety Beliefs** | `expected_network_recovery_s`                    | 180 s (~3 min)                                  | Worst-case natural recovery time for ONT/modem/router/WAN                        | 120–300 s                                                  | How long we give the network to self-recover before considering escalation. |
|                           | `escalation_buffer_s`                            | 60 s (~1 min)                                   | Extra tolerance for transient instability                                        | 30–120 s                                                   | Prevents premature destructive actions during brief flaps. |
|                           | `reboot_settle_delay_s`                          | 30 s                                            | Delay after power-off before power-on                                            | 15–60 s                                                    | Hardware protection (capacitor discharge, boot time). |
|                           | `recovery_cooldown_s`                            | 1800 s (30 min)                                 | Minimum time between physical recovery attempts                                  | 900–3600 s (15–60 min)                                     | Prevents relay thrashing / power supply stress. Conservative for longevity. |
| **Derived / Computed**    | `escalation_delay_s`                             | `expected_network_recovery_s + escalation_buffer_s` | Total sustained DOWN time before escalation allowed                              | Computed — do not override directly                        | Encodes “how long is reasonable to wait before drastic action?” |
|                           | `fast_poll_nominal_interval_s`                   | `CYCLE_INTERVAL_S × FAST_POLL_SCALAR`           | Nominal fast interval (no jitter)                                                | Computed                                                       | Used to conservatively calculate escalation threshold. |
|                           | `max_consecutive_down_before_escalation`         | `ceil(escalation_delay_s / fast_poll_nominal_interval_s)` | Number of DOWN cycles needed before physical recovery                           | Computed                                                       | Jitter-robust; assumes fastest possible confirmation cadence → conservative escalation. |
| **Assumptions**           | Cloudflare TTL & API limits                      | 60 s TTL, generous but finite rate limits       | DNS can change every ~60 s; API calls should be minimized                        | N/A                                                        | All timing decisions are built around this reality. |
|                           | Residential WAN instability                      | Frequent transient outages (seconds to minutes) | Expect blips, DHCP churn, ISP flaps — not permanent failures                     | N/A                                                        | Drives fast poll + hysteresis + fail-fast design. |
|                           | Hardware recovery time                           | ONT/modem/router/WAN usually recovers in <3 min | Physical reboot rarely needed if given time                                      | N/A                                                        | Basis for `expected_network_recovery_s` buffer. |

### Quick Tuning Philosophy

**Goal:** Knowledge is power — but power comes at a cost.

- **Cheap & fast** → local cache, LAN pings, internal counters  
- **Expensive & slow** → external DoH, ipify, Cloudflare API mutation  
- **Decision rule:** Use cheap/fast signals first → escalate to expensive only when confidence is low or evidence is contradictory  
- **Adaptive heartbeat** — fast when sick (recovery priority), slow when healthy (I/O minimization)  
- **Fail-safe bias** — monotonic FSM + gating + conservative escalation → never act without proof

**Happy tuning!**  
Tune aggressively only if you understand your ISP stability, hardware boot times, and Cloudflare usage patterns.  
Conservative defaults are chosen for safety and longevity.

See also: [RecoveryPolicy.py](./recovery_policy.py) – escalation beliefs & derived math