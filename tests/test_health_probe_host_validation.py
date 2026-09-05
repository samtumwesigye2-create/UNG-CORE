from pathlib import Path


def test_health_and_ready_bypass_host_gate():
    source = Path("app/main.py").read_text()
    assert 'request.url.path not in {"/health", "/ready"}' in source
    assert 'invalid host header' in source


def test_normal_requests_still_validate_hosts():
    source = Path("app/main.py").read_text()
    assert "def _host_allowed" in source
    assert "fnmatch(hostname, pattern)" in source
    assert "request.headers.get(\"host\", \"\")" in source
