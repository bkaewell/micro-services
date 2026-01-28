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


