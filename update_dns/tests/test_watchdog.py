import pytest
import responses
from unittest.mock import patch
from update_dns.watchdog import check_internet, reset_smart_plug

# ===========================================
# Fixture to mock os.system calls (i.e. ping) 
# ===========================================
@pytest.fixture
def mock_ping(monkeypatch):
    def _mock_ping(return_code):
        monkeypatch.setattr("os.system", lambda cmd: return_code)
    return _mock_ping

def test_check_internet_valid(mock_ping):
    # Simulate a successful ping result
    mock_ping(0) # mock os.system returns 0 (success)
    host = "8.8.8.8"
    assert(check_internet(host)) is True

def test_check_internet_invalid(mock_ping):
    # Simulate a failed ping result
    mock_ping(1) # mock os.system returns nonzero (failure)
    host = ""
    assert(check_internet(host)) is False


# # =====================================
# # Fixture to bypass time.sleep globally
# # =====================================
# @pytest.fixture(autouse=True)
# def no_sleep(monkeypatch):
#     monkeypatch.setattr("update_dns.watchdog.time.sleep", lambda x: None)

@responses.activate
@patch("update_dns.watchdog.time.sleep", return_value=None)
#def test_reset_smart_plug_success(no_sleep):
def test_reset_smart_plug_success(_):
    # Simulate smart plug OK responses to both off/on endpoint calls
    PLUG_IP="192.168.0.150"
    responses.add(responses.GET, f"http://{PLUG_IP}/relay/0?turn=off", status=200)
    responses.add(responses.GET, f"http://{PLUG_IP}/relay/0?turn=on", status=200)
    assert reset_smart_plug() is True


@responses.activate
@patch("update_dns.watchdog.time.sleep", return_value=None)
#def test_reset_smart_plug_failure(no_sleep):
def test_reset_smart_plug_failure(_):
    # Simulate smart plug failing to respond properly (non-200 or exception)
    PLUG_IP="192.168.0.150"
    responses.add(responses.GET, f"http://{PLUG_IP}/relay/0?turn=off", status=500)
    responses.add(responses.GET, f"http://{PLUG_IP}/relay/0?turn=on", status=200)
    reset_smart_plug() is False

