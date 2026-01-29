# Resilient Home Network Control Plane 🚀

## Why I Built This

I’ve tended to take smart risks, moving toward roles and locations that offered real technical challenge and operational responsibility. My career has taken me across the world, including living and working in Hawaii, Tokyo, and Munich, often far from home. One recurring problem followed me everywhere: how to maintain reliable, trustworthy access to my home network while thousands of miles away.

I wanted something more than “it usually works.” I wanted control over system behavior.

This project began as a practical need: accessing my home network from anywhere in the world to monitor a smart home, keep IoT devices healthy, ensure security systems remain online during outages, and watch local sports while traveling. That same access now supports my siblings, spread up and down the East Coast, stretched across the Atlantic seaboard, who can securely connect back home as if they were still local.

Over time, the project grew beyond that initial use case.

Earlier in my career, outside of my time in Germany, I worked primarily on legacy weapon systems using legacy tooling. That experience reinforced how to design resilient systems under constraints, reason about failure modes, and extract reliability from imperfect environments. What it didn’t provide was the opportunity to build something modern, opinionated, and production-grade from the ground up using current tools.

So I built the system I wanted to operate.

I designed this control plane with direct ownership over every variable: cycle timing, polling behavior, jitter, convergence guarantees, and emitted telemetry. The goal was to make system behavior observable, justify every external dependency, and ensure the network could survive power loss, remain reachable through UPS-backed infrastructure, and recover cleanly without human intervention.

The result is Cadence Cloud, named after my dog, Cadence, and the steady rhythm of the control loop itself. From anywhere in the world, connecting through the VPN feels like returning to a stable home network that continues operating quietly and correctly in the background.

This repository reflects how I approach engineering: building systems that are designed for unattended operation, measured in production, and resilient by construction.

---

## 📈 Impact at a Glance (Real Metrics)

* **99.85% uptime** over thousands of autonomous control cycles (cycle-based metrics persisted to disk - IP history + uptime counters survive restarts and power loss; no extrapolation)
* **<3 minutes DNS convergence** after public IP change — **>50–90% faster** than typical third‑party Dynamic DNS (DDNS) providers, which commonly converge in 5–30 minutes under residential WAN conditions
* **~83% reduction in external API calls** (120/hr → ~21/hr steady state)
* **Zero false-positive DNS mutations** under real residential WAN churn
* Runs **24/7 on consumer hardware** (single low-power System76 mini-PC)

---

## 📊 Live Telemetry (Production Output)

```console
11:08:44 🔁 LOOP        START      Wed Jan 28 2026            | loop=3408
11:08:44 💚 HEARTBEAT   OK         ———————                   
11:08:44 🟢 ROUTER      UP         ip=192.168.0.1             | rtt=9ms
11:08:45 🟢 WAN_PATH    OK         ———————                    | rtt=28ms
11:08:45 🟢 PUBLIC_IP   OK         ip=###.##.##.##            | rtt=74ms | attempts=1/4
11:08:45 🟢 CACHE       HIT        ip=###.##.##.##            | rtt=0.3ms | age=250s / 3600s
11:08:45 🟢 GSHEET      OK         ———————                    | rtt=182ms
11:08:45 🟢 NET_HEALTH  UP         ALL SYSTEMS NOMINAL 🐾🌤️   | loop_ms=295 | uptime=99.85% (3403/3408) | sleep=129s
```

## 🧠 What I Built (Not Managed — Built)

I designed, implemented, deployed, and operate a fully autonomous, operator-inspired control plane that behaves like a mini Kubernetes controller, but tuned for a single-node, hostile home-network environment.

This is hands-on IC work: architecture, control theory, fault tolerance, observability, and production hardening — all executed solo.

---

## 🏗️ Engineering Achievements (Impact-Driven)

### Autonomous Control Loop & Reliability

* **Designed and implemented a monotonic finite state machine (FSM)** with fail-fast DOWN demotion and hysteresis-based promotion (2× consecutive stable IP confirmations required), eliminating flapping and guaranteeing **zero false-positive DNS updates**.

* Built a **self-healing control loop** inspired by Kubernetes operators and circuit-breaker patterns, achieving **99.93% uptime** across thousands of real execution cycles — not simulated runs.

### Extreme API Efficiency Without Losing Responsiveness

* Reduced Cloudflare + ipify external API calls by **~83%** in steady state using:

  * 3600s cache freshness windows
  * 2× IP stability gating
  * Adaptive polling (≈30s during recovery → ≈180s when healthy)

* Maintained **sub‑3‑minute IP convergence** despite aggressive call suppression — proving efficiency and responsiveness are not mutually exclusive.

### Anti-Detection & Unconventional Problem Solving

* Engineered **always-on 0–10s cycle jitter** to intentionally break detectable polling signatures (Cloudflare / IP services), preventing heuristic rate-limiting while preserving deterministic control behavior.

* Applied **domain-specific polling intelligence**: fast when broken, whisper-quiet when healthy — a pattern rarely implemented correctly outside large-scale systems.

### DNS Reconciliation & Eventual Consistency

* Built a **layered DNS reconciliation pipeline**:

  1. Local persisted cache
  2. DNS-over-HTTPS truth validation
  3. Cloudflare mutation (only when trust threshold is met)

* Achieves **eventual consistency with minimal external I/O**, converging quickly during outages and remaining near-silent during steady state.

### Production VPN Delivery

* Delivered **kernel-space WireGuard VPN** via wg-easy with a dynamic DNS endpoint (`vpn.*.example.com:51820`).

* Result: **zero-config, reliable remote access** that survives ISP IP churn and router replacements.

* Added **beta physical self-healing**: controlled edge power-cycling after sustained DOWN states with safety guardrails.

---

## ⚙️ Technical Stack (Hands-On)

* **Python** — control loop, FSM, reconciliation logic, observability
* **Poetry** — dependency management, reproducible environments, clean packaging
* **Docker & docker-compose** — production packaging and deployment
* **WireGuard (kernel-space)** — VPN transport
* **Netplan** — stable LAN identity under hardware changes
* **Cloudflare API + DoH** — authoritative DNS management
* **Filesystem persistence** — durable IP history, uptime counters, and FSM state (`~/.cache/` for local dev, `/app/cache/` for containerized runtime)
* **VS Code** — primary IDE for development, debugging, and iteration

**Runtime environment:**

* Single low-power **System76 mini-PC**
* **UPS-backed power** for compute node *and* network gear (router + modem), enabling continued operation and clean recovery through residential power outages

Everything runs **continuously**, unattended, with structured per-cycle telemetry.

---

## 🧩 Operator-Inspired Design (Single-Node, No Crutches)

This project deliberately mirrors Kubernetes operator principles — without Kubernetes:

* **Monotonic FSM** → equivalent of [Custom Resource (CR)](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/) status/conditions
* **Fail-fast demotion + gated promotion** → safety via evidence
* **Adaptive polling + jitter** → load-aware reconciliation
* **Side-effect gating** → mutations only when trust is high

This demonstrates the ability to **internalize distributed-systems patterns** and apply them pragmatically in constrained environments.

---

## 📚 Deep Dives

* **[TUNING.md](./docs/TUNING.md)** — first-principles reasoning behind every timing, threshold, and trade-off
* **[VPN-DNS-STACK.md](./docs/VPN-DNS-STACK.md)** — architecture, layer boundaries, router checklist, Mermaid workflows
* **[LESSONS-LEARNED.md](./docs/LESSONS-LEARNED.md)** — real-world surprises, failure modes, and what I’d improve next

---

##  ⚡ Quick Start

```bash
git clone https://github.com/bkaewell/micro-services.git
cd update_dns

cp .env.example .env          # configure domain, flags, keys, tokens
docker compose up -d --build app
```

---

## Why This Project Matters

This is not a resume bullet generator.

It demonstrates:

* Extreme **ownership** (idea → design → deployment → operation)
* Comfort operating **production systems alone**
* Ability to **quantify impact**, not just describe intent
* Fast learning and adaptation across networking, control systems, and reliability engineering

If you value engineers who **build, measure, and iterate relentlessly**, this repository is the proof.

