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

network_autopilot/
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
poetry run python -c "import network_autopilot; print(network_autopilot.__file__)"
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
