## Quick Setup

This repository contains:
- **Source Code:** The main Python script.
- **Environment Template:** A `.env.example` file containing placeholder config values
- **Deployment Script:** A `deploy.sh` script that sets up a separate production directory (with logs and cron job subdirectories) so that private data and runtime files remain outside of your repository.
This script also copies the `.env.example` to `.env` if no `.env` exists.

> **Important:**  
> In the deployed (production) directory, the main script **and** the `.env` file must reside in the same folder so that the script can properly read its config.

---

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup the .env File

Create a private/uncommitted `.env` file in the same directory as the script and add the following variables:

```ini
GOOGLE_SHEET_NAME=Name of your Google Sheet
GOOGLE_API_CREDENTIALS=Path to your Google service account JSON file
```

### 3. Run the Script

```bash
python extract_public_ip_address.py
```
