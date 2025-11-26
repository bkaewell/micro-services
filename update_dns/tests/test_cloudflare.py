import os
import pytest
import requests
import responses

from unittest.mock import patch, MagicMock

from update_dns.cloudflare import CloudflareClient


import pytest
import os
from unittest.mock import patch


@patch.dict(os.environ, {
    "CLOUDFLARE_API_BASE_URL": "https://mock.api.com/v4",
    "CLOUDFLARE_API_TOKEN": "mock_token",
    "CLOUDFLARE_ZONE_ID": "mock_zone",
    "CLOUDFLARE_DNS_NAME": "mock.hostname.com"
})
def test_client_init_and_url_builder_smoke():
    """
    Smoke test: Confirms successful client instantiation and execution of the 
    core _build_resource_url helper
    """
    # Instantiate the Client (triggers os.getenv() calls)
    client = CloudflareClient()

    # Execute the core logic helper (happy path: collection GET)
    result_url = client._build_resource_url(is_collection=True)

    # 3. Assert minimal expected output
    expected_substring = "https://mock.api.com/v4/zones/mock_zone/dns_records?name=mock.hostname.com&type=A"
    
    assert result_url == expected_substring
    assert client.headers["Authorization"] == "Bearer mock_token"


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


# @patch.dict(os.environ, {
#     "CLOUDFLARE_API_BASE_URL": "https://api.cloudflare.com/client/v4",
#     "CLOUDFLARE_ZONE_ID": "aaa111",
#     "CLOUDFLARE_DNS_NAME": "vpn.starbase.com"
# })
# @responses.activate
# def test_get_dns_record_info():

#     # Mock HTTP responses for relay OFF/ON commands
#     responses.add(responses.GET, "https://api.cloudflare.com/client/v4/zones/aaa111/dns_records?name=vpn.starbase.com&type=A", status=200)

#     client = CloudflareClient()
#     client.get_dns_record_info()

#     assert True


# def test_update_dns_record_info():

#     client = CloudflareClient()
#     client.update_dns_record("123", "1.1.1.1")


#     assert True


