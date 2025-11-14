import pytest
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
    """Patch Config and time.sleep for all tests in this module."""
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
    router_ip = MockConfig.Hardware.ROUTER_IP
    plug_ip = MockConfig.Hardware.PLUG_IP
    reboot_delay = MockConfig.Hardware.REBOOT_DELAY
    init_delay = MockConfig.Hardware.INIT_DELAY

    # Mock HTTP responses for relay OFF/ON commands
    responses.add(responses.GET, f"http://{plug_ip}/relay/0?turn=off", status=status_plug_off)
    responses.add(responses.GET, f"http://{plug_ip}/relay/0?turn=on", status=status_plug_on)

    result = reset_smart_plug()

    assert result is expected_result


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
