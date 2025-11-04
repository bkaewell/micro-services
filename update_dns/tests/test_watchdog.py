import pytest
import responses
from update_dns.watchdog import check_internet, reset_smart_plug


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


