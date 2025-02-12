## Quick Setup

This repository contains:
- **Requirements:** List of Python library dependencies required to run the main Python script.
- **Source Code:** The main Python script.
- **Environment Template:** A `.env.example` file containing placeholder config values.
- **Deployment Script:** A `deploy.sh` script that sets up a separate production directory (with logs and cron job subdirectories) so that private data and runtime files remain outside of your repository.
This script also copies the `.env.example` to `.env` if no `.env` exists.

> **Important:**  
> In the deployed (production) directory, the main script **and** the `.env` file must reside in the same folder so that the script can properly read its config.

---

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Your Environment via Deployment

Simply run the deployment script. The `deploy.sh` script will:

- Create or update your production directory (e.g., `~/deployed_extract_public_ip`).
- Create necessary subdirectories such as `logs` and `cron_job`.
- If a `.env` file does not exist in the production directory, it will copy `.env.example` to `.env`.

After running the deployment script, update the newly created `.env` file in the production directory with your actual configuration values (i.e., your private data and credentials).

```ini
GOOGLE_SHEET_NAME=Name of your Google Sheet
GOOGLE_API_CREDENTIALS=Path to your Google service account JSON file
```

Run the deployment script with:

```bash
./deploy.sh
```

### 3. Run the Script

Once deployed, run the script from the production directory:

```bash
python ~/deployed_extract_public_ip/extract_public_ip_address.py
```

### 4. Set Up a Cron Job

TBD
```ini
0 18 * * * cd ~/deployed_extract_public_ip && /usr/bin/python extract_public_ip_address.py >> logs/cron.log 2>&1
```
