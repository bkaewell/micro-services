
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
