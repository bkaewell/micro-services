import pytest
from update_dns.watchdog import check_internet

def test_check_internet_valid(monkeypatch):
    # Simulate a successful ping result
    # Mock os.system to return 0 (success)
    monkeypatch.setattr("os.system", lambda cmd: 0)
    host = "8.8.8.8"
    assert(check_internet(host)) is True

def test_check_internet_invalid(monkeypatch):
    # Simulate a failed ping result
    monkeypatch.setattr("os.system", lambda cmd: 1)
    host = ""
    assert(check_internet(host)) is False