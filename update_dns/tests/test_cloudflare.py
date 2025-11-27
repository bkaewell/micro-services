import os
import pytest
import requests
import responses

from unittest.mock import patch

from update_dns.cloudflare import CloudflareClient


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


@patch.dict(os.environ, {
    "CLOUDFLARE_API_BASE_URL": "https://api.cloudflare.com/client/v4",
    "CLOUDFLARE_API_TOKEN": "mock_token",
    "CLOUDFLARE_ZONE_ID": "aaa111",
    "CLOUDFLARE_DNS_NAME": "vpn.starbase.com"
})
@responses.activate
def test_get_dns_record_info():
    """Tests successful fetching of DNS record info by mocking the API response."""
    
    # Define the EXPECTED response body for a successful Cloudflare GET call
    # Cloudflare returns a dictionary containing a 'result' list
    mock_response_data = {
        "success": True,
        "errors": [],
        "messages": [],
        "result": [{
            "id": "fff000",
            "type": "A",
            "name": "vpn.starbase.com",
            "content": "1.2.3.4",
            "modified_on": "2025-01-01T00:00:00Z"
        }]
    }

    # Register the Mock HTTP Response with the JSON payload.
    responses.add(
        method=responses.GET,
        url="https://api.cloudflare.com/client/v4/zones/aaa111/dns_records?name=vpn.starbase.com&type=A",
        json=mock_response_data,
        status=200
    )

    client = CloudflareClient()
    result = client.get_dns_record_info()

    assert result['id'] == "fff000"
    assert len(responses.calls) == 1

# --- Mock Constants ---
MOCK_BASE_URL = "https://api.cloudflare.com/client/v4/zones/aaa111/dns_records?name=vpn.starbase.com&type=A"

# --- Test Data ---
SUCCESS_RESPONSE_BODY = {
    "success": True,
    "result": [{
        "id": "fff000",
        "type": "A",
        "content": "1.2.3.4",
        "modified_on": "2025-01-01T00:00:00Z"
    }]
}

EMPTY_RESPONSE_BODY = {
    "success": True,
    "result": []
}

FAILURE_RESPONSE_BODY = {
    "success": False, 
    "errors": [{"message": "Authentication error"}]
}

# --- Parametrized Test Cases ---
@pytest.mark.parametrize(
    "status_code, response_body, expected_exception, expected_record_id",
    [
        # ✅ Success - should return the record ID and no exception
        (200, SUCCESS_RESPONSE_BODY, None, "fff000"),

        # ⚠️ Record notfound - API is successful (HTTP 200), but returns an empty list
        # This checks the 'if not records_list:' logic, raising RuntimeError
        (200, EMPTY_RESPONSE_BODY, RuntimeError, None),

        # ❌ API authentication failure
        # This checks the 'resp.raise_for_status()' logic, raising RequestException
        (403, FAILURE_RESPONSE_BODY, RuntimeError, None), 
    ],
)
@patch.dict(os.environ, {
    "CLOUDFLARE_API_BASE_URL": "https://api.cloudflare.com/client/v4",
    "CLOUDFLARE_API_TOKEN": "mock_token",
    "CLOUDFLARE_ZONE_ID": "aaa111",
    "CLOUDFLARE_DNS_NAME": "vpn.starbase.com"
})
@responses.activate
def test_get_dns_record_info(
    status_code, response_body, expected_exception, expected_record_id
):
    """
    Tests get_dns_record_info across success, record not found and API failure
    scenarios
    """
    
    # Register the mock HTTP response
    responses.add(
        method=responses.GET,
        url=MOCK_BASE_URL,
        json=response_body,
        status=status_code
    )

    # Instantiate the client
    client = CloudflareClient()
    
    # Execution and assertion logic
    if expected_exception:
        # Assert that the function raises the specified error
        with pytest.raises(expected_exception):
            client.get_dns_record_info()
    else:
        # Assert the function returns the correct record data
        result = client.get_dns_record_info() 
        assert result['id'] == expected_record_id
        assert result['content'] == "1.2.3.4"
        assert len(responses.calls) == 1





# def test_update_dns_record_info():

#     client = CloudflareClient()
#     client.update_dns_record("123", "1.1.1.1")


#     assert True
