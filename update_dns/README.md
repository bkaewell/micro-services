# Resilient Home Network Control Plane 🚀

## Why I Built This

I’ve always taken **smart risks** — moving where the work and learning were hardest and most interesting. My career has taken me across the world, living and working in **Hawaii, Tokyo, and Munich**, often far from home. One constant problem followed me everywhere: *how do I maintain assured, trustworthy access to my home network when I’m thousands of miles away?*

I wanted something more than "it usually works." I wanted **full control**.

This project started as a very real need: reliably accessing my home network from anywhere in the world — to monitor a smart home, keep IoT devices healthy, ensure security systems stay online during outages, and yes, **watch my local sports teams no matter what continent I’m on**. That same assured access also benefits my siblings, now scattered up and down the East Coast — stretched across the Atlantic seaboard like distant lighthouses — who can securely connect back home as if they never left.

But it quickly became something deeper.

Earlier in my career, outside of my time in Germany, I spent years working on **legacy weapon systems with legacy tooling**. That experience taught me how to engineer around constraints, design resilient systems with limited tools, and extract reliability from imperfect environments. What it didn’t give me was space to build something modern, opinionated, and production-grade — end to end — using today’s tooling.

So I decided to build exactly the system I wished existed.

I designed this control plane with **intentional ownership over every variable**: cycle timing, polling behavior, jitter, convergence guarantees, and high-signal telemetry. I wanted to see the system think. I wanted every external API call to be justified. I wanted the network to **survive power loss**, stay reachable via **UPS-backed infrastructure**, and recover cleanly without human intervention.

The result is **Cadence Cloud** — named after my yellow lab, *Cadence*, and the rhythmic heartbeat of the control loop itself. From anywhere in the world, connecting through the VPN feels like stepping back into my home network — steady, reliable, and quietly doing its job. The cloud connects me home; the cadence keeps it honest.

This repository isn’t a hobby script. It’s a **production-grade system built with purpose** — a demonstration of how I think, how I build, and how I ship.


