import pytest
import responses
from unittest.mock import patch
from update_dns.watchdog import check_internet, reset_smart_plug


# ========
# FIXTURES
# ========

# -------------------------
# Mock for os.system (ping)
# -------------------------
@pytest.fixture
def mock_ping(monkeypatch):
    """Patch os.system to simulate ping return codes (0=success, non-zero=failure)"""
    def _mock_ping(return_code):
        monkeypatch.setattr("os.system", lambda cmd: return_code)
    return _mock_ping

# -------------------
# Minimal Config Mock
# -------------------
class MockConfig:
    class Hardware:
        PLUG_IP = "192.168.0.150"
        REBOOT_DELAY = 1

# ---------------------------------------------
# Fixture to patch Config and bypass time.sleep
# ---------------------------------------------
@pytest.fixture(autouse=True)
def mock_config_and_no_sleep():
    """Automatically patch time.sleep and Config throughout all tests in this module"""
    with patch("update_dns.watchdog.time.sleep", return_value=None), \
         patch("update_dns.watchdog.Config", MockConfig):
        yield


# =================================
# TEST GROUP: Internet Connectivity
# =================================
def test_check_internet_online(mock_ping):
    """Verify check_internet() returns True when host is reachable"""
    mock_ping(0)
    host = "8.8.8.8"

    assert(check_internet(host)) is True

def test_check_internet_offline(mock_ping):
    """Verify check_internet() returns False when host is unreachable"""
    mock_ping(1)
    host = ""

    assert(check_internet(host)) is False


# ============================
# TEST GROUP: Smart Plug Reset
# ============================
@responses.activate
def test_reset_smart_plug_success():
    """Simulate smart plug OK responses to both off/on endpoint calls"""
    ip = MockConfig.Hardware.PLUG_IP
    responses.add(responses.GET, f"http://{ip}/relay/0?turn=off", status=200)
    responses.add(responses.GET, f"http://{ip}/relay/0?turn=on", status=200)
    
    result = reset_smart_plug()
    assert len(responses.calls) == 2
    assert result is True

@responses.activate
def test_reset_smart_plug_failure():
    """Simulate smart plug failing to respond properly (non-200 or exception)"""
    ip = MockConfig.Hardware.PLUG_IP
    responses.add(responses.GET, f"http://{ip}/relay/0?turn=off", status=500)
    responses.add(responses.GET, f"http://{ip}/relay/0?turn=on", status=200)
    
    result = reset_smart_plug()
    assert len(responses.calls) == 2
    assert result is False
