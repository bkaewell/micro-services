import pathlib
import json
from typing import Dict, Any, Union

# --- 1. Centralized Cache Directory Setup ---
# When running locally, pathlib.Path.home() points to your macOS home directory.
# When running in Docker, it points to the container user's home directory (e.g., /home/user or /root),
# which is the correct, writeable location for application data within the container.
CACHE_DIR = pathlib.Path.home() / ".cache" / "update_dns"
CACHE_DIR.mkdir(parents=True, exist_ok=True) 

# --- 2. Specific Cache File Paths ---
CLOUDFLARE_IP_FILE = CACHE_DIR / "cloudflare_ip.json"
GOOGLE_SHEET_ID_FILE = CACHE_DIR / 'google_sheet_id.txt'

# --- 3. Cloudflare IP Cache Functions ---
def _read_json_file(file_path: pathlib.Path) -> Dict[str, Any]:
    """Helper function to safely read and parse a JSON file"""
    if file_path.exists():
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # Log error if needed, but return empty dict to proceed gracefully
            return {}
    return {}

def _write_json_file(file_path: pathlib.Path, data: Dict[str, Any]):
    """Helper function to safely write data to a JSON file"""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError:
        # Log error if file write fails
        pass

def get_cloudflare_ip() -> str:
    """Reads the last known public IP from the Cloudflare cache file"""
    data = _read_json_file(CLOUDFLARE_IP_FILE)
    return data.get("last_ip", "")

def update_cloudflare_ip(new_ip: str):
    """Writes the new IP to the Cloudflare cache file upon successful DNS update"""
    data = {"last_ip": new_ip}
    _write_json_file(CLOUDFLARE_IP_FILE, data)
