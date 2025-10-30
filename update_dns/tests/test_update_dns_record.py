
# Example tests:

# 1. IP changed → record updated
# 2. IP unchanged → no update
# 3. Record not found → ValueError
# 4. Invalid API key / error response → raises exception


# def test_api(mocker):
#     mock_get = mocker.patch("requests.get")
#     mock_get.return_value.status_code = 200
#     mock_get.return_value.text = "8.8.8.8"
#     ...

# def test_update_dns_record(mocker):
#     mock_get = mocker.patch("requests.get")
#     mock_put = mocker.patch("requests.put")

#     # Fake Cloudflare record JSON
#     mock_get.return_value.status_code = 200
#     mock_get.return_value.json.return_value = {
#         "result": [{"id": "abc123", "type": "A", "content": "1.2.3.4", "modified_on": "2025-09-05T00:50:37Z"}],
#         "result_info": {"total_count": 1}
#     }

#     mock_put.return_value.status_code = 200

#     # Call your function
#     updated = update_dns_record(cloudflare_config, "5.6.7.8")
#     assert updated is True


import pytest
import responses

from network_autopilot.network_autopilot import update_dns_record

def test_update_dns_record():

    

    assert update_dns_record() is expected







# def update_dns_record(cloudflare_config,
#                       detected_ip: str,
#                       version: str = "ipv4") -> dict:
#     """
#     Update the Cloudflare DNS record ('A' for IPv4, 'AAAA' for IPv6) 
#     to the detected IP if it has changed

#     Returns: 
#         dictionary
#     """

#     api_base_url = cloudflare_config["api_base_url"]
#     api_token    = cloudflare_config["api_token"]
#     zone_id      = cloudflare_config["zone_id"]
#     dns_name     = cloudflare_config["dns_name"]

#     # Add comment here
#     record_type = "A" if version.lower() == "ipv4" else "AAAA"

#     # Get DNS record 
#     dns_records_url = f"{api_base_url}/zones/{zone_id}/dns_records?name={dns_name}"

#     # Cloudflare API request: authentication headers + DNS record payload
#     header = {
#         "Authorization": f"Bearer {api_token}",
#         "Content-Type" : "application/json",
#     }
#     data = {
#         "type"   : record_type,   # DNS record type (i.e. A, AAAA)
#         "name"   : dns_name,      # DNS record name
#         "content": detected_ip,   # Public IP to update
#         "ttl"    : 60,            # TTL = Time-to-Live 
#         "proxied": False          # Grey cloud (not proxied thru Cloudflare)
#     }

#     # Authenticate with API token
#     resp = requests.get(dns_records_url, headers=header)     
#     resp.raise_for_status()
#     print(f"update_dns_record: DNS records URL: {dns_records_url}")         #####
#     print(f"update_dns_record: DNS records JSON response:\n{json.dumps(resp.json(), indent=2)}")    #####

#     # Extract the list of DNS records from the Cloudflare response
#     records = resp.json().get("result", [])

#     # Find the record that matches the desired type (A or AAAA)
#     record = next((r for r in records if r.get("type") == record_type), None)

#     if record:
#         record_id         = record["id"]
#         dns_record_ip     = record["content"]
#         dns_last_modified = record["modified_on"]

#         print(f"✅ Found {record_type} record: id={record_id}, ip={dns_record_ip}, modified_on={dns_last_modified}")
#     else:
#         print(f"❌ No {record_type} record found for {dns_name}")
#         record_id = dns_record_ip = dns_last_modified = None

#     # Update DNS record if IP has changed
#     if dns_record_ip != detected_ip:
#         update_url = f"{api_base_url}/zones/{zone_id}/dns_records/{record_id}"
#         resp = requests.put(update_url, headers=header, json=data)
#         resp.raise_for_status()
#         print(f"update_dns_record: ✅  Updated '{dns_name}': {dns_record_ip} → {detected_ip}")       #####
#         #return True
#     else:
#         print(f"update_dns_record: ℹ️  No update needed for '{dns_name}', IP unchanged")             #####
#         #return False
    
#     return {
#         "dns_name"         : dns_name,
#         "detected_ip"      : detected_ip,
#         "dns_last_modified": format_cloudflare_timestamp(dns_last_modified)
#     }


