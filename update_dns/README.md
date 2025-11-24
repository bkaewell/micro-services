# 🚀 Autonomous Network Management Agent Microservice
A lightweight, containerized microservice for **IP address ingestion, processing, and third-party API integration.** Designed with **scalability, automation, and real-time monitoring** in mind.
  
  
## 📌 Features
- **Process IP Address Data:** Efficiently ingest and store IP-related data for analytics
- **Integrate with External APIs:** Supports Google Services, ip-api, and more
- **Automated & On-Demand Execution:** Run as a **scheduled cron job** or **manually**
- **Containerized Deployment:** Fully Dockerized for seamless deployment
- **Logging & Monitoring:** Supports **real-time logs for operational insights**
  
  
## ⚡ Quick Setup
### Clone the repo
```bash
git clone https://github.com/bkaewell/micro-services.git
cd micro-services/ip_upload
```

### Set up environment variables
```bash
cp .env.example .env
```
Update `.env` to configure **API keys, Google filenames/worksheet tabs, location mappings, and cron settings.**

### (Optional) Set up Google API key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable required APIs (i.e. Google Sheets, Google Maps, Cloud Vision, etc.)
3. Generate an API key under APIs & Services > Credentials
4. Add the API key to the `.env`
5. (Optional) Secure your API key:
In the API key settings, [restrict usage](https://cloud.google.com/docs/authentication/api-keys#securing) (i.e. by HTTP referrers or IP addresses) for enhanced security
  
  
## 🐳 Containerization
This microservice is **containerized using Docker** and **orchestrated with Docker Compose** for both **manual execution and scheduled automation.**
### Run the Service in Two Modes
```bash
# Start both manual (`app`) and automated cron (`cron`) services
docker-compose up --build -d
```
To run **only one mode,** specify the service:
```bash
docker-compose up app -d   # Manual test mode
docker-compose up cron -d  # Scheduled cron job mode
```
To **stop all running services:**
```bash
docker-compose down
```
  
  
## ⚙️ DevOps & Automation
🕒 Cron Job Schedule (`cron/mycron`) -- runs once per day @ 23:59 New York time:
```bash
59 23 * * * /usr/local/bin/python3 /app/src/ip_upload.py >> /var/log/cron.log 2>&1
```

### Cron Job Integration
1. `cron/mycron` → Defines the schedule
2. `docker-entrypoint.sh` → Determines whether to start cron or execute manually
3. `docker-compose.yaml` → Defines the cron job as a separate service


## 👨‍💻 Development
For debugging or running the script locally **without Docker,** you can execute manually:
```bash
pip install -r requirements.txt
python src/ip_upload.py
```
  
  
## 🛠 Deployment & Monitoring
This microservice supports **real-time observability** using Docker logs.

### Production Deployment
Deploy in **detached mode** to run in the background:
```bash
docker-compose up -d
```
Verify running services:
```bash
docker ps
```

### Real-time Logs & Monitoring
Monitor logs for **manual execution (`app`)** or **cron execution (`cron`):**
```bash
docker logs -f <ip_uploader_app | ip_uploader_cron>
```
For more details:
```bash
docker-compose logs --tail=100 -f
```
  
  
## 🧨 Testing (TBD)
### Run Unit Tests
```bash
pytest tests/
```

### Run Manual IP Upload Test
```bash
docker exec -it ip_uploader_app python /app/src/ip_upload.py
```
  
  
## 📂 Repository Overview
```

update_dns/
├── tests/                  # Unit tests
├─ __main__.py             # Runs the loop
├─ network_autopilot.py    # Orchestrates all logic
├─ watchdog.py             # Internet check & smart plug reset
├─ cloudflare.py           # Cloudflare + Sheets logic
├─ sheets.py               # Google Sheets updates
├─ db.py                   # SQLite metrics (optional)
├─ utils.py                # Helpers (ping, time, IP fetch)

├── docker-entrypoint.sh    # Controls execution (manual vs. cron)
├── Dockerfile              # Containerization
├── .env.example            # Sample env file
├── README.md               
└── docker-compose.yaml     # Docker setup

```
  
  
## Why This Microservice?
Designed for **scalability, efficiency, and ease of deployment,** this service simplifies **IP data ingestion** with robust API integrations and a containerized environment.



Verify package visibility (without full run):
```
poetry run python -c "import update_dns; print(update_dns.__file__)"
```

poetry check


Dockerfile:
# -------------------------------------------------------------------
# 4. Install Python dependencies (cached and no dev deps in prod)
# -------------------------------------------------------------------
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-interaction --no-ansi --no-root
# For production without dev dependencies, uncomment:
#RUN poetry install --no-root --without dev

DNS Leak test
IP leak test




Development (live editing, base first, override second extends settings from the first base):
```
docker compose up -d --build


docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build
```

Production (frozen code):
```
docker compose -f docker-compose.yaml up -d
```

docker compose up -d --build


docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build manual_run



Step 1: Build the Docker image
Make sure you’re in your project root where your Dockerfile is:
```
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml build test
```

Step 2: Run the container with an interactive shell
Instead of running the normal Python command, override it to get a shell:
```
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run --rm test /bin/bash
```
- --rm → automatically deletes the container when you exit, keeps things clean
- /bin/bash → opens a Bash shell inside the container

Now you’re inside the container

Step 3: Inspect environment variables
Inside the container:
```
printenv
```

Step 4: Test your Python script
Still inside the container, run:
```
python -m update_dns.__main__
```
- If you set PYTHONUNBUFFERED=1 in the dev compose file, your print statements will show immediately

Step 5: Exit the container
```
exit
```
- If you used --rm, the container is deleted automatically

Python package directory: micro-service/update_dns/src/update_dns/...


🌐 Update DNS Microservice

A lightweight, containerized service that monitors your public IP address and automatically updates DNS records when changes are detected. Designed for dynamic networks, remote systems, and self-hosted setups that need reliable domain availability.

📌 Features

Dynamic DNS Updates: Detects IP changes and syncs records via Cloudflare API

Smart Network Watchdog: Periodically checks internet connectivity and resets hardware if needed

Automated or Manual Execution: Run continuously or trigger on demand

Containerized Deployment: Optimized Docker setup for local or distributed environments

Logging & Observability: Provides clear, real-time runtime output for debugging and operations





Test locally:
```
poetry run python -m update_dns.__main__
```


Deployed production code:
docker compose build app
docker compose run --rm app /bin/bash
printenv
python -m update_dns.__main__

Deployed dev code:
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml build test
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run --rm test /bin/bash
printenv
python -m update_dns.__main__


Cleaned up stale .venv/
~/repo/micro-services/update_dns/
rm -fr .venv
poetry config virtualenvs.in-project true
poetry env use python3.14
poetry install --with dev
poetry env info
poetry run which python
poetry run which pytest
poetry run pytest

poetry run pytest -v
poetry run pytest tests/test_to_local_time.py
poetry run pytest -v tests/test_watchdog.py

# Check Container Logs for Exceptions
docker logs vpn_ddns_cron | tail -n 200


# Logging Style Quick Reference
| Level       | Emoji | 
| ----------- | ----- |
| `INFO`      | 🟢    |
| `WARNING`   | ⚠️    |
| `ERROR`     | ❌    | 
| `EXCEPTION` | 🔥    | 


Get into the OSI model network architecture (7 layers) for the purpose of this script...

Check Method	Why It's Best for Recovery:
check_internet() (Simple Ping/DNS)	This is the minimum viable test. You only need confirmation that Layer 3 (Network) and possibly basic Layer 4 (Transport) are operational. It requires fewer network resources and is faster than HTTPS.

get_public_ip() (HTTPS API Call)	This is an application-layer test that checks Layers 5-7 (Session, Presentation, Application). If the router is still slow or resolving DNS poorly right after a reboot, this more complex check might fail even if the connection is fundamentally back online.



## 🛡️ Self-Healing Dynamic DNS & Network Watchdog 🧭

This project employs a robust, multi-layered approach to guarantee network stability and accurate DNS synchronization, leveraging the **OSI 7-Layer Model** to intelligently diagnose and recover from failures.

### The Problem: False Negatives and Unreliable Checks

In dynamic DNS (DDNS) systems, a simple internet failure can temporarily halt service. Traditional checks often rely on low-level pings, which can return "OK" even if high-level services are failing, leading to false negatives and missed DNS updates.

### The Solution: Layered Validation and Methodical Recovery

Our agent executes the network check and self-healing in three distinct phases, moving up and down the network stack:

#### 1. Primary Health Check (Layers 5-7: Application)

* **Action:** The main loop's first task is to execute **`get_public_ip()`**. This involves an HTTPS request to an external API (like IPify).
* **Rationale:** Success requires the entire network stack to be functional: DNS resolution, TCP handshakes, SSL negotiation, and application-layer communication. If this **Layer 7** test succeeds, we have the highest confidence that the internet is fully operational for the DNS update.
* **Failure Trigger:** If this high-level check fails, it signals a systemic network issue, triggering the watchdog.

#### 2. Watchdog Recovery Check (Layers 3 & 4: Transport/Network)

If the primary check fails, the **Watchdog** system attempts a self-healing reboot of the smart plug, followed by a two-phase network verification:

* **Phase A: Router Check (LAN Health)**
    * **Action:** Ping the local **router IP** (e.g., `192.168.1.1`).
    * **Rationale:** This confirms the local physical connection (Layer 1/2) is back and the router's **Layer 3** stack is responding on the LAN side.
* **Phase B: External Check (WAN Health)**
    * **Action:** Ping a reliable external host like **`8.8.8.8`**.
    * **Rationale:** This confirms the router has successfully established its **WAN link** with the ISP and can forward packets to the internet (a full **Layer 3** confirmation). 

[Image of the OSI Model showing Network and Application Layers]


Only when both the local and external checks pass does the Watchdog declare the system healthy and allow the main DNS loop to resume.

#### 3. Diagnostic Logging & Resilience

This methodical approach minimizes false negatives and provides better diagnostic logging during self-healing: The log clearly shows which layer (Application, Router, or WAN) failed, leading to faster troubleshooting. The recovery process is resilient, checking the local network *before* wasting attempts on the external WAN link.
