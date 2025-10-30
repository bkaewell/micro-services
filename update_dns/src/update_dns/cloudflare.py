import requests
#from feature.config import Config

def sync_dns(ip_address: str):
    # url = f"https://api.cloudflare.com/client/v4/zones/{Config.CLOUDFLARE_ZONE_ID}/dns_records"
    # headers = {"Authorization": f"Bearer {Config.CLOUDFLARE_API_TOKEN}"}
    # # NOTE: You’ll need to identify the record_id via Cloudflare API or config

    # response = requests.put(
    #     f"{url}/RECORD_ID",
    #     headers=headers,
    #     json={"content": ip_address, "type": "A", "name": "example.domain.com"},
    # )

    # if response.ok:
    #     print(f"✅ Updated Cloudflare DNS to {ip_address}")
    # else:
    #     print(f"❌ Failed DNS update: {response.text}")

    # return response.ok

    return True
