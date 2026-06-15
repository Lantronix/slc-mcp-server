import pytest
from unittest.mock import MagicMock, patch
from slc_mcp.providers import CredentialError


def _make_manager(ip="10.0.0.1"):
    from slc_mcp.session import SessionManager
    mgr = SessionManager.__new__(SessionManager)
    mgr._sessions = {}
    provider = MagicMock()
    provider.get_credentials.return_value = {"ip": ip, "username": "admin", "password": "pw", "totp_secret": None}
    mgr._provider = provider
    return mgr, provider


def test_cache_miss_authenticates():
    mgr, provider = _make_manager()
    with patch("slc_mcp.client.login", return_value="newtok") as mock_login:
        session = mgr.get_or_create("device-1")
    assert session.token == "newtok"
    assert session.ip == "10.0.0.1"
    mock_login.assert_called_once_with("10.0.0.1", "admin", "pw", totp_secret=None)


def test_cache_hit_skips_login():
    mgr, provider = _make_manager()
    with patch("slc_mcp.client.login", return_value="tok1"):
        mgr.get_or_create("device-1")
    with patch("slc_mcp.client.login", return_value="tok2") as mock_login:
        session = mgr.get_or_create("device-1")
    assert session.token == "tok1"
    mock_login.assert_not_called()


def test_invalidate_forces_reauth():
    mgr, provider = _make_manager()
    with patch("slc_mcp.client.login", return_value="tok1"):
        mgr.get_or_create("device-1")
    mgr.invalidate("device-1")
    with patch("slc_mcp.client.login", return_value="tok2"):
        session = mgr.get_or_create("device-1")
    assert session.token == "tok2"


def test_clear_all_empties_sessions():
    mgr, provider = _make_manager()
    with patch("slc_mcp.client.login", return_value="tok"):
        mgr.get_or_create("device-1")
        mgr.get_or_create("device-2")
    mgr.clear_all()
    assert len(mgr._sessions) == 0


def test_credential_error_propagates():
    mgr, provider = _make_manager()
    provider.get_credentials.side_effect = CredentialError("no creds")
    with pytest.raises(CredentialError, match="no creds"):
        mgr.get_or_create("device-1")


def test_set_provider_clears_sessions():
    mgr, _ = _make_manager()
    with patch("slc_mcp.client.login", return_value="tok"):
        mgr.get_or_create("device-1")
    new_provider = MagicMock()
    mgr.set_provider(new_provider)
    assert len(mgr._sessions) == 0
    assert mgr._provider is new_provider


def test_totp_secret_passed_to_login():
    """When creds include a totp_secret, it's forwarded to client.login."""
    from slc_mcp.session import SessionManager
    mgr = SessionManager.__new__(SessionManager)
    mgr._sessions = {}
    provider = MagicMock()
    provider.get_credentials.return_value = {
        "ip": "10.0.0.1",
        "username": "admin",
        "password": "pw",
        "totp_secret": "JBSWY3DPEHPK3PXP",
    }
    mgr._provider = provider
    with patch("slc_mcp.client.login", return_value="tok") as mock_login:
        mgr.get_or_create("device-1")
    mock_login.assert_called_once_with("10.0.0.1", "admin", "pw", totp_secret="JBSWY3DPEHPK3PXP")
