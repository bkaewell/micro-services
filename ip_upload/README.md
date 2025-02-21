# IP Upload Microservice

This document provides a quick setup guide for the **IP Upload** microservice. This service handles IP address data ingestion and processing while integrating with third-party APIs (such as Google Services) to extend its capabilities.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- (Optional) Python 3.x for local development

## Quick Setup

### 1. Clone the repo and navigate to this directory:
```bash
git clone https://github.com/bkaewell/micro-services.git
cd micro-services/ip_upload
```

### 2. Duplicate the sample environment file:
```bash
cp .env.example .env
```

Open the `.env` file and update the configuration values. Be sure to set any necessary API keys (e.g., for Google Services) and other environment-specific parameters.

### 3. Set up a Google services API key

If you plan to enable Google Services for additional functionalities, follow these steps:

1. Create or Select a Google Cloud Project:

Visit the Google Cloud Console.
Create a new project or select an existing one.

2. Enable the Required APIs:

Navigate to APIs & Services > Library.
Enable the API you need (e.g., Google Maps API, Cloud Vision API, etc.).

3. Generate an API Key:

Go to APIs & Services > Credentials.

Click Create Credentials and select API Key.

Copy the generated API key and add it to your .env file, for example:

```dotenv
GOOGLE_API_KEY=your_api_key_here
```

4. Secure Your API Key:

In the API key settings, restrict usage (e.g., by HTTP referrers or IP addresses) for enhanced security.

## Running the Service
### Using Docker Compose
1. Build and Start the Service:

```bash
docker-compose up --build
```

2. Stop the Service:

```bash
docker-compose down
```

### Running Locally (Without Docker)
1. Install Dependencies:

```bash
pip install -r requirements.txt
```

2. Run the IP Upload Scripts:

Standard IP upload:

```bash
python src/ip_upload.py
```

## Deployment Considerations
For production deployments, we recommend using Docker Compose to ensure consistency across environments. Verify that all environment variables are correctly set and secure before deployment.

## Testing
Basic test scaffolding is provided in the `tests/` directory. To run tests, use your preferred testing framework (i.e. pytest):

```bash
pytest tests/
```

## Cron Jobs
The `cron/` directory is reserved for scheduled tasks. Configure and integrate cron jobs as needed for automated operations.



```
# IP Upload Microservice Repository Structure

ip_upload/                         # IP Upload microservice
├── .env                           # Environment variable file (not committed)
├── .env.example                   # Sample environment file for reference
├── Dockerfile                     # Docker image configuration
├── README.md                      # Detailed setup & deployment instructions for IP Upload (this file)
├── docker-compose.yaml            # Docker Compose file for multi-container deployment
├── requirements.txt               # Python dependencies list
├── cron/                          # Directory for scheduled jobs
│   └── .gitkeep                   # Placeholder to retain empty directory in Git
├── src/                           # Source code directory
│   ├── ip_upload.py               # Core script for IP Upload functionality
│   └── ip_upload_with_logging.py  # Extended script with logging capabilities
└── tests/                         # Directory for test cases
    └── .gitkeep                   # Placeholder to retain empty test directory in Git
```
