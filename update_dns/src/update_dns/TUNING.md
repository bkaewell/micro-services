## Time Budget & Tuning Guide

These parameters form the agent's **adaptive heartbeat** — balancing quick recovery during outages with minimal external I/O in steady state.  

The system is designed around Cloudflare's 60-second TTL:  
- We never poll meaningfully faster than TTL (avoids false positives)  
- We aggressively recover when unhealthy  
- We become very quiet and thrifty when healthy  

| Parameter                        | Default     | Purpose & Effect                                                                 | Tuning Guidance                                                                 | Interdependencies & Engineering Notes                                                                 |
|----------------------------------|-------------|----------------------------------------------------------------------------------|---------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| `CYCLE_INTERVAL_S`               | 65 s        | Base cycle length in steady state (UP).                                          | 60–120 s<br>Should be ≥ TTL (60 s) to avoid false drift detection              | Core heartbeat. Too fast → unnecessary DoH/API calls. Too slow → delayed recovery. Chosen just above TTL for safety margin. |
| `FAST_POLL_SCALAR`               | 0.5         | Multiplier during DOWN/DEGRADED → ~2× faster polling (~32.5 s cycles)           | 0.3–0.8<br>Lower = more aggressive recovery                                     | Enables rapid detection & recovery. Combined with jitter, keeps API load reasonable even when "fast". |
| `SLOW_POLL_SCALAR`               | 2.0         | Multiplier in steady UP → ~2× slower polling (~130 s cycles)                    | 1.5–3.0<br>Higher = more I/O savings                                            | The biggest win for long-term API thriftiness. Turns agent into a very quiet observer when healthy. |
| `POLLING_JITTER_S`               | 5 s         | ± random offset added to every interval                                          | 3–10 s<br>Smaller = tighter pattern; larger = more human-like                  | Clever anti-rate-limit defense. Makes calls appear random/natural even with adaptive intervals. |
| `MAX_CACHE_AGE_S`                | 600 s (10 min) | Max age before cached DNS IP is considered stale → forces DoH re-verification | 300–900 s (5–15 min)<br>~5× TTL is safe sweet spot                              | Saves expensive DoH calls in steady state (~5–8 cycles between checks). Forces refresh during long offline → catches external changes. |
| `CLOUDFLARE_MIN_TTL_S`           | 60 s        | Cloudflare's minimum TTL for unproxied records (hard limit)                     | Fixed (non-tunable)                                                             | Foundation of all timing decisions. Cycle interval ≥ TTL prevents chasing false drift. |
| `API_TIMEOUT_S`                  | 8 s         | Timeout for all external HTTP/DoH calls                                          | 5–12 s                                                                          | Safety net. Too low → false negatives; too high → hangs cycle. 8 s is proven balanced for residential networks. |
| `REBOOT_DELAY_S`                 | 30 s        | Delay between power-off and power-on during physical recovery                   | 15–60 s<br>Depends on device boot time                                          | Hardware protection. Long enough for capacitors to discharge, short enough for quick recovery. |
| `RECOVERY_COOLDOWN_S`            | 1800 s (30 min) | Minimum time between physical recovery attempts                                 | 900–3600 s (15–60 min)<br>Higher = more hardware safety                         | Prevents relay thrashing / power supply stress. 30 min is conservative for home hardware longevity. |

### Quick Tuning Philosophy

- **Healthy (UP)** → very slow + jittered polling + long cache life → **extremely low I/O** (goal: near-zero unnecessary API calls)
- **Unhealthy** → fast polling → **quick detection & recovery**
- **Safety everywhere** → TTL-aware intervals, cache freshness checks, cooldowns, timeouts
- **Human-like behavior** → jitter prevents pattern-based rate limiting

These values are deliberately conservative defaults — tune aggressively only if you understand your hardware, ISP stability, and Cloudflare usage patterns.

Happy tuning!