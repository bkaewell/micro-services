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
@pytest.fixture(autouse=True)   #apply to every test in module
def mock_config_and_no_sleep():
    """Automatically patch time.sleep and Config throughout all tests in this module"""
    with patch("update_dns.watchdog.time.sleep", return_value=None), \
         patch("update_dns.watchdog.Config", MockConfig):
        yield


# =================================
# TEST GROUP: Internet Connectivity
# =================================
# Function under test: check_internet()
# -------------------------------------
@pytest.mark.parametrize(
    "host, ping_return_code, expected_result",
    [
        ("8.8.8.8", 0, True),
        ("", 1, False),
    ],
)
def test_check_internet(mock_ping, host, ping_return_code, expected_result):
    """Verify check_internet() returns True when host is reachable"""
    mock_ping(ping_return_code)
    result = check_internet(host)

    assert expected_result is result


# ============================
# TEST GROUP: Smart Plug Reset
# ============================
# Function under test: reset_smart_plug()
# ---------------------------------------
@pytest.mark.parametrize(
    "status_plug_off, status_plug_on, expected_result",
    [
        (200, 200, True),   # Both OK → success
        (500, 200, False),  # OFF/ON → fails
        (200, 500, False),  # ON/OFF → fails
        (500, 500, False),  # Both OFF → fails
    ],
)
@responses.activate
def test_reset_smart_plug(status_plug_off, status_plug_on, expected_result):
    """Simulate various HTTP GET requests to smart plug API endpoints"""
    ip = MockConfig.Hardware.PLUG_IP
    responses.add(responses.GET, f"http://{ip}/relay/0?turn=off", status=status_plug_off)
    responses.add(responses.GET, f"http://{ip}/relay/0?turn=on", status=status_plug_on)
    result = reset_smart_plug()

    # assert len(responses.calls) == 2
    assert result is expected_result
