# IP Upload Microservice 🚀

A lightweight, containerized microservice for **IP address ingestion, processing, and third-party API integration**.

## **📌 Features**
- **Process IP Address Data**: Efficiently process IP data for analytics or storage
- **Integrate with External APIs**: Supports Google Services, ip-api, and more
- **Containerized Deployment**: Fully Dockerized for seamless deployment

## **⚡ Quick Setup**
### 1. Clone the repo 
```bash
git clone https://github.com/bkaewell/micro-services.git
cd micro-services/ip_upload
```

### 2. Set up environment variables
```bash
cp .env.example .env
```
Update `.env` with your API keys and configuration

### 3. (Optional) Set up Google API key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable required APIs (i.e. Google Sheets, Google Maps, Cloud Vision, etc.)
3. Generate an API key under APIs & Services > Credentials
4. Add it to `.env`:

```dotenv
GOOGLE_API_KEY=your_api_key_here
```
5. (Optional) Secure your API key:
In the API key settings, [restrict usage](https://cloud.google.com/docs/authentication/api-keys#securing) (i.e. by HTTP referrers or IP addresses) for enhanced security

## **🚀 Running the Service**
### Using Docker Compose
1. Build and Start the Service

```bash
docker-compose up --build
```

2. Stop the Service

```bash
docker-compose down
```

### Running Locally (Without Docker)

```bash
pip install -r requirements.txt
python src/ip_upload.py
```
## **🛠 Deployment & Testing**

**- Production Deployment:** Use Docker Compose for consistency
**- Run Tests:**

```bash
pytest tests/
```

**##🔄 Cron Job**
The `cron/` directory is reserved for scheduled tasks. Configure and integrate cron jobs as needed for automated operations.

## **📂 Repository Overview**
```
ip_upload/
├── src/                # IP processing scripts
├── tests/              # Unit tests
├── Dockerfile          # Containerization
├── .env.example        # Sample env file
├── README.md           # This file
└── docker-compose.yaml # Docker setup
```

## **📌 Why This Microservice?**
Designed for **scalability, efficiency, and ease of deployment,** this service simplifies **IP data ingestion** with robust API integrations and a containerized environment
