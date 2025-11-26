import os
import pytest

from unittest.mock import patch, MagicMock

from update_dns.config import Config
from update_dns.cloudflare import CloudflareClient


@pytest.mark.parametrize(
    "is_collection, record_id, expected_url, should_raise_error",
    [
        # ... (same test cases as before) ...
        (True, None, "https://api.cloudflare.com/client/v4/zones/aaa111/dns_records?name=vpn.starbase.com&type=A", False),
        (False, "fff000", "https://api.cloudflare.com/client/v4/zones/aaa111/dns_records/fff000", False),
        (False, None, None, True), 
    ],
)
@patch.dict(os.environ, {
    "CLOUDFLARE_API_BASE_URL": "https://api.cloudflare.com/client/v4",
    "CLOUDFLARE_ZONE_ID": "aaa111",
    "CLOUDFLARE_DNS_NAME": "vpn.starbase.com"
})
def test_build_resource_url_integration(is_collection, record_id, expected_url, should_raise_error):
    """
    Tests the _build_resource_url() method to ensure it correctly constructs 
    the Cloudflare List (GET) and Single Resource (PUT) URLs
    
    This test verifies proper concatenation of base path, zone ID, record ID, 
    and query filters, while confirming configuration is correctly loaded 
    from the patched os.environ
    """

    # Instantiate the client
    client = CloudflareClient()

    if should_raise_error:
        with pytest.raises(ValueError):
            client._build_resource_url(is_collection, record_id)
    else:
        result = client._build_resource_url(is_collection, record_id)
        
        assert result == expected_url



