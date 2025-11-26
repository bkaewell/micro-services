import json
import requests

from .config import Config
from .logger import get_logger
from .utils import to_local_time
from .cache import get_cloudflare_ip, update_cloudflare_ip


class CloudflareClient:
    """Handles all communication and logic specific to the Cloudflare DNS API"""
    
    def __init__(self, config):
        """Initializes the client with configuration and logging dependency"""

        # Define the logger once for the entire class
        self.logger = get_logger("cloudflare")
        self.config = config

        # Pre-calculated and necessary instance variables
        self.headers = {
            "Authorization": f"Bearer {config.API_TOKEN}",
            "Content-Type": "application/json",
        }
        self.api_base_url = config.API_BASE_URL
        self.zone_id = config.ZONE_ID
        self.dns_name = config.DNS_NAME
        self.record_type = "A"   # Fixed type
        self.ttl = 60    # Time-to-Live
        self.proxied = False   # Grey cloud icon (not proxied thru Cloudflare)

