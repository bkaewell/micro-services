import pytest
import requests
import responses
from unittest.mock import patch
from update_dns.watchdog import check_internet, reset_smart_plug


# ========
# FIXTURES
# ========

# -------------------
# Minimal Config Mock
# -------------------
class MockConfig:
    class Hardware:
        ROUTER_IP="1.1.1.1"
        PLUG_IP = "2.2.2.2"
        REBOOT_DELAY = 1
        INIT_DELAY = 1

# Fixture to patch Config and bypass time.sleep
@pytest.fixture(autouse=True)
def patch_config_and_sleep():
    """Patch Config and time.sleep for all tests in this module"""
    with patch("update_dns.watchdog.Config", MockConfig), \
         patch("update_dns.watchdog.time.sleep", return_value=None) as mock_sleep:
        yield mock_sleep  # yield mock_sleep if you want to assert the delay


# ============================
# TEST GROUP: Smart Plug Reset
# ============================
# Function: reset_smart_plug()
# ----------------------------
@pytest.mark.parametrize(
    "status_plug_off, status_plug_on, expected_result",
    [
        # ✅ Both relay endpoints respond OK (200)
        (200, 200, True),

        # ❌ OFF relay fails (500)
        (500, 200, False),

        # ❌ ON relay fails (500)
        (200, 500, False), 

        # ❌ Both relay endpoints unreachable (500/500)
        (500, 500, False), 
    ],
)

@responses.activate
def test_reset_smart_plug(status_plug_off, status_plug_on, expected_result):
    """Verify smart plug reset behavior for different HTTP responses"""

    # Mock HTTP responses for relay OFF/ON commands
    responses.add(responses.GET, f"http://{MockConfig.Hardware.PLUG_IP}/relay/0?turn=off", status=status_plug_off)
    responses.add(responses.GET, f"http://{MockConfig.Hardware.PLUG_IP}/relay/0?turn=on", status=status_plug_on)

    result = reset_smart_plug()

    assert result is expected_result

@responses.activate
@patch("update_dns.watchdog.check_internet", return_value=True)
def test_reset_smart_plug_router_online(mock_check):
    """Router becomes reachable - should return True even if plug reset succeeds"""
    responses.add(responses.GET, f"http://{MockConfig.Hardware.PLUG_IP}/relay/0?turn=off", status=200)
    responses.add(responses.GET, f"http://{MockConfig.Hardware.PLUG_IP}/relay/0?turn=on", status=200)

    assert reset_smart_plug() is True
    mock_check.assert_called()  # or assert call count

@responses.activate
@patch("update_dns.watchdog.check_internet", return_value=False)
def test_reset_smart_plug_router_offline(mock_check):
    """Router remains unreachable after reset attempts - should return False"""
    responses.add(responses.GET, f"http://{MockConfig.Hardware.PLUG_IP}/relay/0?turn=off", status=200)
    responses.add(responses.GET, f"http://{MockConfig.Hardware.PLUG_IP}/relay/0?turn=on", status=200)

    assert reset_smart_plug() is False
    assert mock_check.call_count == 5  # verify retry behavior


@patch("requests.get", side_effect=requests.exceptions.RequestException("Boom"))
def test_reset_smart_plug_request_exception(mock_get):
    """Simulate network failure during relay calls"""

    assert reset_smart_plug() is False


@patch("update_dns.watchdog.requests.get", side_effect=ValueError("Unexpected"))
def test_reset_smart_plug_unexpected_exception(mock_get):
    """Simulate unexpected exception to reach generic exception handler"""

    assert reset_smart_plug() is False


# =================================
# TEST GROUP: Internet Connectivity
# =================================
# Function: check_internet()
# --------------------------
@pytest.mark.parametrize(
    "host, ping_return_code, expected_result",
    [
        # ✅ Host reachable (ping returns 0)
        ("8.8.8.8", 0, True),

        # ❌ Host unreachable (ping returns non-zero)
        ("", 1, False),
    ],
)

def test_check_internet(host, ping_return_code, expected_result, monkeypatch):
    """Verify check_internet() correctly reflects host reachability"""

    # Patch os.system inline, only for this test
    monkeypatch.setattr("os.system", lambda cmd: ping_return_code)

    result = check_internet(host)

    assert expected_result is result
