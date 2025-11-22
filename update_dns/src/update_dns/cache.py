import json
import pathlib
from typing import Dict, Any

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
    """Helper function to safely read and parse a JSON file using pathlib"""

    if not file_path.exists():
        return {}
    
    try:
        # Get the content as a single string
        content = file_path.read_text()
        return json.loads(content)
    except (json.JSONDecodeError, OSError):
        # OSError handles permission issues or other file I/O errors (like IOError)
        return {}

def _write_json_file(file_path: pathlib.Path, data: Dict[str, Any]):
    """Helper function to safely write data to a JSON file using pathlib"""
    try:
        content = json.dumps(data, indent=4)
        file_path.write_text(content)
    except OSError:
        # Log error if file write fails (like IOError)
        pass

def get_cloudflare_ip() -> str:
    """Reads the last known public IP from the Cloudflare cache file"""
    data = _read_json_file(CLOUDFLARE_IP_FILE)
    return data.get("last_ip", "")

def update_cloudflare_ip(new_ip: str):
    """Writes the new IP to the Cloudflare cache file upon successful DNS update"""
    data = {"last_ip": new_ip}
    _write_json_file(CLOUDFLARE_IP_FILE, data)
