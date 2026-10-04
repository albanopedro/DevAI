import pytest

from devai.web.security import (
    SECURITY_HEADERS,
    host_allowed,
    hostname,
    new_token,
    origin_allowed,
    token_matches,
)


def test_tokens_are_long_and_different():
    first, second = new_token(), new_token()

    assert first != second
    assert len(first) >= 40


def test_token_matches():
    assert token_matches("abc", "abc") is True
    assert token_matches("abd", "abc") is False
    assert token_matches(None, "abc") is False
    assert token_matches("", "abc") is False


@pytest.mark.parametrize(
    ("host", "name"),
    [
        ("127.0.0.1:8765", "127.0.0.1"),
        ("localhost", "localhost"),
        ("LOCALHOST:80", "localhost"),
        ("[::1]:8765", "::1"),
        ("evil.example:8765", "evil.example"),
    ],
)
def test_hostname(host, name):
    assert hostname(host) == name


@pytest.mark.parametrize(
    "host", ["127.0.0.1:8765", "localhost:9000", "[::1]:8765", "localhost"]
)
def test_local_hosts_on_any_port(host):
    assert host_allowed(host) is True


@pytest.mark.parametrize(
    "host",
    [
        None,
        "",
        "evil.example",
        "evil.example:8765",  # DNS rebinding: the attacker's name still shows here
        "127.0.0.1.evil.example",
        "localhost.evil.example",
        "192.168.0.10:8765",
    ],
)
def test_other_hosts_are_refused(host):
    assert host_allowed(host) is False


def test_origins():
    assert origin_allowed(None, "127.0.0.1:8765") is True  # not a browser
    assert origin_allowed("http://127.0.0.1:8765", "127.0.0.1:8765") is True
    assert origin_allowed("http://evil.example", "127.0.0.1:8765") is False
    assert origin_allowed("http://localhost:8765", "127.0.0.1:8765") is False
    assert origin_allowed("null", "127.0.0.1:8765") is False


def test_the_page_may_load_only_its_own_files():
    policy = SECURITY_HEADERS["Content-Security-Policy"]

    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert SECURITY_HEADERS["Referrer-Policy"] == "no-referrer"
