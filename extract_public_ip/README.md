~~~markdown
# How to Use This Script - `extract_public_ip_address.py`

## 1. Install Dependencies

Run the following command to install the required dependencies:

```bash
pip install -r requirements.txt
```

## 2. Setup the `.env` File

Create a `.env` file in the same directory as the script and add the following variables:

```ini
GOOGLE_SHEET_NAME=Name of your Google Sheet
GOOGLE_API_CREDENTIALS=Path to your Google service account JSON file.
LOG_DIR=~/automated_scripts
```

## 3. Run the Script

Execute the script using Python:

```bash
python extract_public_ip_address.py
```
~~~
