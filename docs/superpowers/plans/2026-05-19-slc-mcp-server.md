# SLC MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP server that exposes the SLC9000 (and SLC8000/EMG) device REST API as 16 MCP tools, with JIT pluggable credential providers and per-device session caching.

**Architecture:** FastMCP wraps all device HTTP calls in `_ok/_err` envelopes; a `SessionManager` caches `device_id → DeviceSession` and re-auths on 401; a `CredentialProvider` ABC with four implementations (env, percepxion, vault, aws) is selected at startup via `SLC_CREDENTIAL_PROVIDER`. All tools accept `device_id: str` as the first parameter.

**Tech Stack:** Python 3.11+, FastMCP, requests, python-dotenv, hvac (optional), boto3 (optional), pytest, responses, pytest-httpserver

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `slc_mcp.py`
- Create: `src/slc_mcp/__init__.py`
- Create: `src/slc_mcp/providers/__init_stub__.py` (placeholder so package is importable)
- Create: `.env.example`
- Create: `.gitignore`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "slc-mcp-server"
version = "0.1.0"
description = "FastMCP server exposing SLC device REST API as MCP tools"
requires-python = ">=3.11"
dependencies = [
  "fastmcp",
  "requests",
  "python-dotenv",
  "hvac",
  "boto3",
]

[project.optional-dependencies]
dev = [
  "pytest",
  "responses",
  "pytest-httpserver",
]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Create requirements.txt**

```
fastmcp
requests
python-dotenv
hvac
boto3
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.py[cod]
.env
*.egg-info/
dist/
.venv/
```

- [ ] **Step 4: Create .env.example**

```bash
# Credential provider: env | percepxion | vault | aws (default: env)
SLC_CREDENTIAL_PROVIDER=env

# Per-device credentials (replace SLC9000_DC_A with your device_id uppercased, hyphens→underscores)
SLC_SLC9000_DC_A_IP=192.168.1.100
SLC_SLC9000_DC_A_USERNAME=admin
SLC_SLC9000_DC_A_PASSWORD=changeme

# Global fallback (single-device setups)
SLC_DEFAULT_IP=192.168.1.100
SLC_USERNAME=admin
SLC_PASSWORD=changeme

# Optional tuning
SLC_REQUEST_TIMEOUT=30
SLC_API_PATH_PREFIX=/api/v2
SLC_VERIFY_SSL=false

# Percepxion provider (only if SLC_CREDENTIAL_PROVIDER=percepxion)
PERCEPXION_API_URL=https://api.consoleflow.com
PERCEPXION_USERNAME=your@email.com
PERCEPXION_PASSWORD=yourpassword

# HashiCorp Vault provider (only if SLC_CREDENTIAL_PROVIDER=vault)
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=hvs.yourtoken

# AWS provider uses standard AWS credential chain (env vars, IAM role, ~/.aws/config)
# AWS_DEFAULT_REGION=us-east-1
```

- [ ] **Step 5: Create package files**

`src/slc_mcp/__init__.py`, empty

`src/slc_mcp/providers/__init_stub__.py`, empty (rename to `__init__.py` in Task 2)

`tests/__init__.py`, empty

- [ ] **Step 6: Create entry point slc_mcp.py**

```python
from slc_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 7: Install in dev mode and verify import**

Run: `cd /mnt/c/Users/rhogg/Projects/git/slc-mcp-server && pip install -e ".[dev]" 2>&1 | tail -5`

Expected: `Successfully installed slc-mcp-server-0.1.0` (or already satisfied)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml requirements.txt slc_mcp.py .env.example .gitignore src/ tests/
git commit -m "feat: project scaffold, pyproject, entry point, package skeleton"
```

---

### Task 2: CredentialProvider ABC + factory

**Files:**
- Create: `src/slc_mcp/providers/__init__.py`
- Create: `tests/providers/__init__.py`
- Create: `tests/providers/test_factory.py`

- [ ] **Step 1: Write the failing test**

`tests/providers/test_factory.py`:

```python
import os
import pytest
from unittest.mock import patch

def test_get_provider_default_is_env():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SLC_CREDENTIAL_PROVIDER", None)
        from importlib import reload
        import slc_mcp.providers as p
        reload(p)
        provider = p.get_provider()
        from slc_mcp.providers.env import EnvCredentialProvider
        assert isinstance(provider, EnvCredentialProvider)

def test_get_provider_unknown_raises():
    with patch.dict(os.environ, {"SLC_CREDENTIAL_PROVIDER": "bogus"}):
        from importlib import reload
        import slc_mcp.providers as p
        reload(p)
        with pytest.raises(p.CredentialError, match="Unknown provider"):
            p.get_provider()

def test_credential_error_is_exception():
    from slc_mcp.providers import CredentialError
    e = CredentialError("test message")
    assert str(e) == "test message"
    assert isinstance(e, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_factory.py -v`
Expected: FAIL, `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write providers/__init__.py**

```python
from abc import ABC, abstractmethod
import os


class CredentialError(Exception):
    pass


class CredentialProvider(ABC):
    @abstractmethod
    def get_credentials(self, device_id: str) -> dict[str, str]:
        """Return {"ip": ..., "username": ..., "password": ...}.
        Raise CredentialError if device_id is unknown or creds are missing."""


def get_provider() -> CredentialProvider:
    name = os.getenv("SLC_CREDENTIAL_PROVIDER", "env").lower()
    if name == "env":
        from slc_mcp.providers.env import EnvCredentialProvider
        return EnvCredentialProvider()
    if name == "percepxion":
        from slc_mcp.providers.percepxion import PercepxionCredentialProvider
        return PercepxionCredentialProvider()
    if name == "vault":
        from slc_mcp.providers.vault import VaultCredentialProvider
        return VaultCredentialProvider()
    if name == "aws":
        from slc_mcp.providers.aws import AWSCredentialProvider
        return AWSCredentialProvider()
    raise CredentialError(
        f"Unknown provider: {name!r}. Set SLC_CREDENTIAL_PROVIDER to: env, percepxion, vault, aws"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_factory.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/providers/__init__.py tests/providers/
git commit -m "feat: CredentialProvider ABC and get_provider() factory"
```

---

### Task 3: EnvCredentialProvider

**Files:**
- Create: `src/slc_mcp/providers/env.py`
- Create: `tests/providers/test_env.py`

- [ ] **Step 1: Write the failing tests**

`tests/providers/test_env.py`:

```python
import os
import pytest
from unittest.mock import patch
from slc_mcp.providers import CredentialError
from slc_mcp.providers.env import EnvCredentialProvider, _device_key


def test_device_key_uppercases_and_replaces():
    assert _device_key("slc9000-dc-a") == "SLC9000_DC_A"
    assert _device_key("device.1") == "DEVICE_1"
    assert _device_key("MY_DEVICE") == "MY_DEVICE"


def test_per_device_env_vars():
    env = {
        "SLC_SLC9000_DC_A_IP": "10.0.0.1",
        "SLC_SLC9000_DC_A_USERNAME": "admin",
        "SLC_SLC9000_DC_A_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        creds = EnvCredentialProvider().get_credentials("slc9000-dc-a")
    assert creds == {"ip": "10.0.0.1", "username": "admin", "password": "secret"}


def test_global_fallback():
    env = {
        "SLC_DEFAULT_IP": "10.0.0.2",
        "SLC_USERNAME": "user",
        "SLC_PASSWORD": "pass",
    }
    with patch.dict(os.environ, env, clear=False):
        creds = EnvCredentialProvider().get_credentials("any-device")
    assert creds["ip"] == "10.0.0.2"
    assert creds["username"] == "user"


def test_missing_env_raises_credential_error():
    clean = {k: "" for k in os.environ if k.startswith("SLC_")}
    with patch.dict(os.environ, clean, clear=False):
        for k in list(os.environ.keys()):
            if k.startswith("SLC_"):
                del os.environ[k]
        with pytest.raises(CredentialError, match="Missing env vars"):
            EnvCredentialProvider().get_credentials("unknown-device")


def test_per_device_overrides_global():
    env = {
        "SLC_DEFAULT_IP": "10.0.0.99",
        "SLC_USERNAME": "global",
        "SLC_PASSWORD": "global",
        "SLC_MYDEV_IP": "10.0.0.5",
        "SLC_MYDEV_USERNAME": "specific",
        "SLC_MYDEV_PASSWORD": "specific",
    }
    with patch.dict(os.environ, env, clear=False):
        creds = EnvCredentialProvider().get_credentials("mydev")
    assert creds["ip"] == "10.0.0.5"
    assert creds["username"] == "specific"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_env.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write providers/env.py**

```python
import os
import re
from slc_mcp.providers import CredentialProvider, CredentialError


def _device_key(device_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()


class EnvCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        key = _device_key(device_id)
        ip = os.getenv(f"SLC_{key}_IP") or os.getenv("SLC_DEFAULT_IP")
        username = os.getenv(f"SLC_{key}_USERNAME") or os.getenv("SLC_USERNAME")
        password = os.getenv(f"SLC_{key}_PASSWORD") or os.getenv("SLC_PASSWORD")
        missing = [
            name
            for name, val in [
                (f"SLC_{key}_IP or SLC_DEFAULT_IP", ip),
                (f"SLC_{key}_USERNAME or SLC_USERNAME", username),
                (f"SLC_{key}_PASSWORD or SLC_PASSWORD", password),
            ]
            if not val
        ]
        if missing:
            raise CredentialError(
                f"Missing env vars for {device_id!r}: {', '.join(missing)}"
            )
        return {"ip": ip, "username": username, "password": password}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_env.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/providers/env.py tests/providers/test_env.py
git commit -m "feat: EnvCredentialProvider with per-device and global fallback"
```

---

### Task 4: SLC API client

**Files:**
- Create: `src/slc_mcp/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_client.py`:

```python
import pytest
import responses as resp_lib
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import slc_mcp.client as client


@dataclass
class FakeSession:
    ip: str = "10.0.0.1"
    token: str = "test-token-abc"
    valid: bool = True


def test_ok_envelope():
    result = client._ok({"key": "value"})
    assert result == {"ok": True, "data": {"key": "value"}}


def test_err_envelope_no_code():
    result = client._err("something failed")
    assert result == {"ok": False, "error": "something failed"}
    assert "status_code" not in result


def test_err_envelope_with_code():
    result = client._err("not found", 404)
    assert result == {"ok": False, "error": "not found", "status_code": 404}


def test_url_builds_correctly():
    with patch.dict("os.environ", {"SLC_API_PATH_PREFIX": "/api/v2"}):
        import importlib
        importlib.reload(client)
        url = client._url("10.0.0.1", "/system/status")
    assert url == "https://10.0.0.1/api/v2/system/status"


@resp_lib.activate
def test_login_success():
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={"token": "tok123", "expires_in": 3600, "user": {"username": "admin"}},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        token = client.login("10.0.0.1", "admin", "password")
    assert token == "tok123"


@resp_lib.activate
def test_login_failure_raises():
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={"error": "invalid credentials"},
        status=401,
    )
    from slc_mcp.providers import CredentialError
    with patch.object(client, "_VERIFY_SSL", False):
        with pytest.raises(CredentialError, match="Login failed"):
            client.login("10.0.0.1", "admin", "wrong")


@resp_lib.activate
def test_get_success():
    resp_lib.add(
        resp_lib.GET,
        "https://10.0.0.1/api/v2/system/status",
        json={"status": "ok"},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is True
    assert result["data"]["status"] == "ok"


@resp_lib.activate
def test_get_401_returns_err():
    resp_lib.add(
        resp_lib.GET,
        "https://10.0.0.1/api/v2/system/status",
        json={},
        status=401,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is False
    assert result["status_code"] == 401
    assert "re-authenticate" in result["error"]


@resp_lib.activate
def test_post_success():
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/config/save",
        json={"status": 200, "code": "SUCCESS", "message": ["2 out of 2 total groups saved"]},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.post(FakeSession(), "/config/save", {})
    assert result["ok"] is True
    assert result["data"]["code"] == "SUCCESS"


def test_get_connection_refused():
    import requests.exceptions
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError()):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is False
    assert "Connection refused" in result["error"]


def test_get_timeout():
    import requests.exceptions
    with patch("requests.get", side_effect=requests.exceptions.Timeout()):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is False
    assert "timed out" in result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_client.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write client.py**

```python
import os
import requests
import urllib3
import logging

from slc_mcp.providers import CredentialError

log = logging.getLogger(__name__)

_TIMEOUT = int(os.getenv("SLC_REQUEST_TIMEOUT", "30"))
_PATH_PREFIX = os.getenv("SLC_API_PATH_PREFIX", "/api/v2")
_VERIFY_SSL = os.getenv("SLC_VERIFY_SSL", "false").lower() not in ("false", "0", "no")

if not _VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _url(ip: str, path: str) -> str:
    return f"https://{ip}{_PATH_PREFIX}{path}"


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data}


def _err(message: str, status_code: int = 0) -> dict:
    result: dict = {"ok": False, "error": message}
    if status_code:
        result["status_code"] = status_code
    return result


def login(ip: str, username: str, password: str) -> str:
    """POST /user/login, return token string. Raise CredentialError on failure."""
    url = _url(ip, "/user/login")
    try:
        r = requests.post(
            url,
            json={"username": username, "password": password},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
    except requests.exceptions.ConnectionError:
        raise CredentialError(f"Connection refused to {ip}, is the device reachable?")
    except requests.exceptions.Timeout:
        raise CredentialError(f"Connection timed out to {ip}")
    if not r.ok:
        raise CredentialError(f"Login failed for {ip}: HTTP {r.status_code}")
    return r.json()["token"]


def get(session, path: str) -> dict:
    try:
        r = requests.get(
            _url(session.ip, path),
            headers={"X-auth-token": session.token},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
    except requests.exceptions.ConnectionError:
        return _err(f"Connection refused to {session.ip}, is the device reachable?")
    except requests.exceptions.Timeout:
        return _err(f"Connection timed out to {session.ip}")
    if r.status_code == 401:
        return _err("Session expired, retry to re-authenticate.", 401)
    if not r.ok:
        return _err(f"HTTP {r.status_code}", r.status_code)
    return _ok(r.json())


def post(session, path: str, body: dict | None = None) -> dict:
    try:
        r = requests.post(
            _url(session.ip, path),
            headers={
                "X-auth-token": session.token,
                "Content-Type": "application/json",
            },
            json=body or {},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
    except requests.exceptions.ConnectionError:
        return _err(f"Connection refused to {session.ip}, is the device reachable?")
    except requests.exceptions.Timeout:
        return _err(f"Connection timed out to {session.ip}")
    if r.status_code == 401:
        return _err("Session expired, retry to re-authenticate.", 401)
    if not r.ok:
        return _err(f"HTTP {r.status_code}", r.status_code)
    return _ok(r.json())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_client.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/client.py tests/test_client.py
git commit -m "feat: SLC API client with _ok/_err envelope, X-auth-token auth, SSL control"
```

---

### Task 5: SessionManager

**Files:**
- Create: `src/slc_mcp/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_session.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from slc_mcp.providers import CredentialError


def _make_manager(ip="10.0.0.1", token="tok"):
    from slc_mcp.session import SessionManager
    mgr = SessionManager.__new__(SessionManager)
    mgr._sessions = {}
    provider = MagicMock()
    provider.get_credentials.return_value = {"ip": ip, "username": "admin", "password": "pw"}
    mgr._provider = provider
    return mgr, provider


def test_cache_miss_authenticates():
    mgr, provider = _make_manager()
    with patch("slc_mcp.client.login", return_value="newtok") as mock_login:
        session = mgr.get_or_create("device-1")
    assert session.token == "newtok"
    assert session.ip == "10.0.0.1"
    mock_login.assert_called_once_with("10.0.0.1", "admin", "pw")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write session.py**

```python
from dataclasses import dataclass

from slc_mcp.providers import CredentialProvider, get_provider


@dataclass
class DeviceSession:
    ip: str
    token: str
    valid: bool = True


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}
        self._provider: CredentialProvider = get_provider()

    def get_or_create(self, device_id: str) -> DeviceSession:
        session = self._sessions.get(device_id)
        if session and session.valid:
            return session
        creds = self._provider.get_credentials(device_id)
        from slc_mcp import client
        token = client.login(creds["ip"], creds["username"], creds["password"])
        session = DeviceSession(ip=creds["ip"], token=token)
        self._sessions[device_id] = session
        return session

    def invalidate(self, device_id: str) -> None:
        session = self._sessions.get(device_id)
        if session:
            session.valid = False

    def clear_all(self) -> None:
        self._sessions.clear()

    def set_provider(self, provider: CredentialProvider) -> None:
        self._provider = provider
        self._sessions.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/session.py tests/test_session.py
git commit -m "feat: SessionManager with cache, invalidation, and provider switching"
```

---

### Task 6: server.py, skeleton, _call helpers, configure_provider

**Files:**
- Create: `src/slc_mcp/server.py`
- Create: `tests/test_server_configure.py`

- [ ] **Step 1: Write the failing test**

`tests/test_server_configure.py`:

```python
import os
from unittest.mock import patch, MagicMock


def test_configure_provider_valid():
    import slc_mcp.server as server
    with patch.object(server._sessions, "set_provider") as mock_set:
        with patch("slc_mcp.server.get_provider", return_value=MagicMock()):
            result = server.configure_provider.__wrapped__("env")
    assert result["ok"] is True
    assert result["data"]["provider"] == "env"


def test_configure_provider_invalid():
    import slc_mcp.server as server
    result = server.configure_provider.__wrapped__("bogus")
    assert result["ok"] is False
    assert "Invalid provider" in result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_configure.py -v`
Expected: FAIL, `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Write server.py skeleton**

```python
import logging
import os
import sys

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

mcp = FastMCP("slc-mcp-server")

from slc_mcp import client
from slc_mcp.providers import CredentialError, get_provider
from slc_mcp.session import SessionManager

_sessions = SessionManager()


def _call_get(device_id: str, path: str) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.get(session, path)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


def _call_post(device_id: str, path: str, body: dict | None = None) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.post(session, path, body)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


@mcp.tool()
def configure_provider(provider: str) -> dict:
    """Switch the active credential provider and clear all cached sessions.
    Valid values: env, percepxion, vault, aws."""
    valid = ("env", "percepxion", "vault", "aws")
    if provider not in valid:
        return client._err(
            f"Invalid provider {provider!r}. Valid values: {', '.join(valid)}"
        )
    os.environ["SLC_CREDENTIAL_PROVIDER"] = provider
    _sessions.set_provider(get_provider())
    return client._ok({"provider": provider, "sessions_cleared": True})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_configure.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/server.py tests/test_server_configure.py
git commit -m "feat: server skeleton with _call helpers and configure_provider tool"
```

---

### Task 7: System and firmware tools

**Files:**
- Modify: `src/slc_mcp/server.py`

- [ ] **Step 1: Add system + firmware tools to server.py (append after configure_provider)**

```python
@mcp.tool()
def get_system_status(device_id: str) -> dict:
    """Get system status for an SLC device."""
    return _call_get(device_id, "/system/status")


@mcp.tool()
def get_system_version(device_id: str) -> dict:
    """Get firmware and software version information for an SLC device."""
    return _call_get(device_id, "/system/version")


@mcp.tool()
def get_network_interfaces(device_id: str) -> dict:
    """Get all network interface configurations and status for an SLC device."""
    return _call_get(device_id, "/network/interfaces")


@mcp.tool()
def get_ztp_status(device_id: str) -> dict:
    """Get Zero Touch Provisioning status for an SLC device."""
    return _call_get(device_id, "/system/ztp")


@mcp.tool()
def get_firmware_version(device_id: str) -> dict:
    """Get installed firmware version for an SLC device."""
    return _call_get(device_id, "/firmware/version")


@mcp.tool()
def get_firmware_update_status(device_id: str) -> dict:
    """Get the status of an in-progress or completed firmware update."""
    return _call_get(device_id, "/firmware/update_status")


@mcp.tool()
def check_firmware_updates(device_id: str) -> dict:
    """Trigger a check for available firmware updates on an SLC device."""
    return _call_post(device_id, "/firmware/check")
```

- [ ] **Step 2: Verify server imports cleanly**

Run: `python -c "from slc_mcp.server import mcp; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/slc_mcp/server.py
git commit -m "feat: system, version, network, ZTP, and firmware MCP tools"
```

---

### Task 8: Port, connection, managed device, and cellular tools

**Files:**
- Modify: `src/slc_mcp/server.py`

- [ ] **Step 1: Add remaining device tools to server.py**

```python
@mcp.tool()
def get_slc_ports(device_id: str) -> dict:
    """Get all serial port configurations and status for an SLC device."""
    return _call_get(device_id, "/ports")


@mcp.tool()
def get_slc_port(device_id: str, port_id: str) -> dict:
    """Get status for a single serial port on an SLC device.
    port_id: port number as a string, e.g. '1' or '16'."""
    return _call_get(device_id, f"/ports/{port_id}/status")


@mcp.tool()
def get_connections(device_id: str) -> dict:
    """Get all active connections on an SLC device."""
    return _call_get(device_id, "/connections")


@mcp.tool()
def get_managed_devices(device_id: str) -> dict:
    """Get inventory of all managed devices connected to an SLC device."""
    return _call_get(device_id, "/managed_devices")


@mcp.tool()
def get_managed_device(device_id: str, managed_device_id: str) -> dict:
    """Get status of a single managed device connected to an SLC device."""
    return _call_get(device_id, f"/managed_devices/{managed_device_id}/status")


@mcp.tool()
def get_cellular_status(device_id: str) -> dict:
    """Get cellular modem status for an SLC device."""
    return _call_get(device_id, "/cellular/status")
```

- [ ] **Step 2: Verify all 16 tools are registered**

Run: `python -c "from slc_mcp.server import mcp; tools = [t for t in dir(mcp) if not t.startswith('_')]; print(len(tools))"`

Actually, count via:
```bash
grep -c "@mcp.tool" src/slc_mcp/server.py
```
Expected: `14` (16 tools total, adding 2 more in Task 9)

- [ ] **Step 3: Commit**

```bash
git add src/slc_mcp/server.py
git commit -m "feat: port, connection, managed device, and cellular MCP tools"
```

---

### Task 9: Config tools (compare_config and save_config)

**Files:**
- Modify: `src/slc_mcp/server.py`
- Create: `tests/test_save_config_guard.py`

- [ ] **Step 1: Write the failing test for save_config confirm guard**

`tests/test_save_config_guard.py`:

```python
def test_save_config_requires_confirm():
    import slc_mcp.server as server
    result = server.save_config.__wrapped__("any-device", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_save_config_confirm_true_calls_device():
    from unittest.mock import patch
    import slc_mcp.server as server
    with patch.object(server, "_call_post", return_value={"ok": True, "data": {"code": "SUCCESS"}}) as mock_post:
        result = server.save_config.__wrapped__("device-1", confirm=True)
    assert result["ok"] is True
    mock_post.assert_called_once_with("device-1", "/config/save")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_save_config_guard.py -v`
Expected: FAIL, `AttributeError` (save_config not yet defined)

- [ ] **Step 3: Add config tools to server.py**

```python
@mcp.tool()
def compare_config(device_id: str) -> dict:
    """Compare running config against saved config on an SLC device."""
    return _call_get(device_id, "/config/compare")


@mcp.tool()
def save_config(device_id: str, confirm: bool = False) -> dict:
    """Save running configuration to non-volatile storage on an SLC device.
    Set confirm=True to proceed. Requires explicit confirmation to prevent accidental writes."""
    if not confirm:
        return client._err(
            "save_config writes to device storage. Call again with confirm=True to proceed."
        )
    return _call_post(device_id, "/config/save")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_save_config_guard.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Verify all 16 tools exist**

Run: `grep -c "@mcp.tool" src/slc_mcp/server.py`
Expected: `16`

- [ ] **Step 6: Commit**

```bash
git add src/slc_mcp/server.py tests/test_save_config_guard.py
git commit -m "feat: compare_config and save_config tools (confirm guard on save)"
```

---

### Task 10: PercepxionCredentialProvider + PercepxionRegistry

**Files:**
- Create: `src/slc_mcp/registry.py`
- Create: `src/slc_mcp/providers/percepxion.py`
- Create: `tests/providers/test_percepxion.py`

- [ ] **Step 1: Write the failing tests**

`tests/providers/test_percepxion.py`:

```python
import os
import pytest
from unittest.mock import patch, MagicMock
from slc_mcp.providers import CredentialError


def test_percepxion_provider_builds_creds():
    mock_registry = MagicMock()
    mock_registry.get_device_ip.return_value = "10.5.0.10"
    env = {
        "SLC_USERNAME": "admin",
        "SLC_PASSWORD": "secret",
    }
    with patch("slc_mcp.providers.percepxion._registry", mock_registry):
        with patch.dict(os.environ, env, clear=False):
            from slc_mcp.providers.percepxion import PercepxionCredentialProvider
            creds = PercepxionCredentialProvider().get_credentials("dc-slc-01")
    assert creds["ip"] == "10.5.0.10"
    assert creds["username"] == "admin"
    mock_registry.get_device_ip.assert_called_once_with("dc-slc-01")


def test_percepxion_provider_missing_creds_raises():
    mock_registry = MagicMock()
    mock_registry.get_device_ip.return_value = "10.5.0.10"
    with patch("slc_mcp.providers.percepxion._registry", mock_registry):
        with patch.dict(os.environ, {}, clear=True):
            from importlib import reload
            import slc_mcp.providers.percepxion as mod
            reload(mod)
            with pytest.raises(CredentialError, match="Missing"):
                mod.PercepxionCredentialProvider().get_credentials("dc-slc-01")


def test_registry_missing_env_raises():
    from slc_mcp.registry import PercepxionRegistry
    with patch.dict(os.environ, {}, clear=True):
        registry = PercepxionRegistry()
        with pytest.raises(CredentialError, match="PERCEPXION_API_URL"):
            registry._login()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_percepxion.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write registry.py**

```python
import logging
import os

import requests

from slc_mcp.providers import CredentialError

log = logging.getLogger(__name__)


class PercepxionRegistry:
    def __init__(self) -> None:
        self._base_url = os.getenv("PERCEPXION_API_URL", "").rstrip("/")
        self._token: str | None = None

    def _login(self) -> str:
        username = os.getenv("PERCEPXION_USERNAME")
        password = os.getenv("PERCEPXION_PASSWORD")
        if not self._base_url or not username or not password:
            raise CredentialError(
                "Percepxion provider requires PERCEPXION_API_URL, PERCEPXION_USERNAME, PERCEPXION_PASSWORD"
            )
        r = requests.post(
            f"{self._base_url}/v1/user/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["token"]

    def get_device_ip(self, device_id: str) -> str:
        if not self._token:
            self._token = self._login()
        headers = {"x-mystq-token": self._token}
        r = requests.get(
            f"{self._base_url}/v3/device/get",
            params={"id": device_id},
            headers=headers,
            timeout=30,
        )
        if r.status_code == 401:
            self._token = self._login()
            headers = {"x-mystq-token": self._token}
            r = requests.get(
                f"{self._base_url}/v3/device/get",
                params={"id": device_id},
                headers=headers,
                timeout=30,
            )
        r.raise_for_status()
        data = r.json()
        ip = data.get("ip") or data.get("address")
        if not ip:
            raise CredentialError(f"Percepxion returned no IP for device {device_id!r}")
        return ip
```

- [ ] **Step 4: Write providers/percepxion.py**

```python
import os
import re

from slc_mcp.providers import CredentialProvider, CredentialError
from slc_mcp.registry import PercepxionRegistry

_registry = PercepxionRegistry()


class PercepxionCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        ip = _registry.get_device_ip(device_id)
        key = re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()
        username = os.getenv(f"SLC_{key}_USERNAME") or os.getenv("SLC_USERNAME")
        password = os.getenv(f"SLC_{key}_PASSWORD") or os.getenv("SLC_PASSWORD")
        if not username or not password:
            raise CredentialError(
                f"Missing SLC_{key}_USERNAME/PASSWORD or SLC_USERNAME/PASSWORD "
                f"for Percepxion provider"
            )
        return {"ip": ip, "username": username, "password": password}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/providers/test_percepxion.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/slc_mcp/registry.py src/slc_mcp/providers/percepxion.py tests/providers/test_percepxion.py
git commit -m "feat: PercepxionCredentialProvider + PercepxionRegistry (IP from Percepxion, creds from env)"
```

---

### Task 11: VaultCredentialProvider

**Files:**
- Create: `src/slc_mcp/providers/vault.py`
- Create: `tests/providers/test_vault.py`

- [ ] **Step 1: Write the failing tests**

`tests/providers/test_vault.py`:

```python
import os
import pytest
from unittest.mock import patch, MagicMock
from slc_mcp.providers import CredentialError
from slc_mcp.providers.vault import VaultCredentialProvider


def test_vault_missing_hvac_raises():
    with patch.dict("sys.modules", {"hvac": None}):
        with pytest.raises(CredentialError, match="hvac is required"):
            VaultCredentialProvider().get_credentials("device-1")


def test_vault_missing_env_raises():
    with patch.dict(os.environ, {}, clear=True):
        mock_hvac = MagicMock()
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            with pytest.raises(CredentialError, match="VAULT_ADDR"):
                VaultCredentialProvider().get_credentials("device-1")


def test_vault_returns_credentials():
    mock_hvac = MagicMock()
    mock_client = MagicMock()
    mock_hvac.Client.return_value = mock_client
    mock_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"ip": "10.1.1.1", "username": "admin", "password": "vaultpass"}}
    }
    env = {"VAULT_ADDR": "https://vault.example.com", "VAULT_TOKEN": "hvs.test"}
    with patch.dict(os.environ, env, clear=False):
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            creds = VaultCredentialProvider().get_credentials("slc9000-dc-a")
    assert creds == {"ip": "10.1.1.1", "username": "admin", "password": "vaultpass"}
    mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(path="slc/slc9000-dc-a")


def test_vault_missing_secret_field_raises():
    mock_hvac = MagicMock()
    mock_client = MagicMock()
    mock_hvac.Client.return_value = mock_client
    mock_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"ip": "10.1.1.1", "username": "admin"}}
    }
    env = {"VAULT_ADDR": "https://vault.example.com", "VAULT_TOKEN": "hvs.test"}
    with patch.dict(os.environ, env, clear=False):
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            with pytest.raises(CredentialError, match="missing field"):
                VaultCredentialProvider().get_credentials("device-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_vault.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write providers/vault.py**

```python
import os

from slc_mcp.providers import CredentialProvider, CredentialError


class VaultCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        try:
            import hvac
        except ImportError:
            raise CredentialError(
                "hvac is required for the vault provider: pip install hvac"
            )
        addr = os.getenv("VAULT_ADDR")
        token = os.getenv("VAULT_TOKEN")
        if not addr or not token:
            raise CredentialError(
                "VAULT_ADDR and VAULT_TOKEN are required for the vault provider"
            )
        vault_client = hvac.Client(url=addr, token=token)
        path = f"slc/{device_id}"
        try:
            secret = vault_client.secrets.kv.v2.read_secret_version(path=path)
            data = secret["data"]["data"]
        except Exception as exc:
            raise CredentialError(
                f"Vault read failed for secret/slc/{device_id}: {exc}"
            ) from exc
        for field in ("ip", "username", "password"):
            if not data.get(field):
                raise CredentialError(
                    f"Vault secret secret/slc/{device_id} missing field: {field!r}"
                )
        return {"ip": data["ip"], "username": data["username"], "password": data["password"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_vault.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/providers/vault.py tests/providers/test_vault.py
git commit -m "feat: VaultCredentialProvider (HashiCorp Vault KV v2)"
```

---

### Task 12: AWSCredentialProvider

**Files:**
- Create: `src/slc_mcp/providers/aws.py`
- Create: `tests/providers/test_aws.py`

- [ ] **Step 1: Write the failing tests**

`tests/providers/test_aws.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from slc_mcp.providers import CredentialError
from slc_mcp.providers.aws import AWSCredentialProvider


def test_aws_missing_boto3_raises():
    with patch.dict("sys.modules", {"boto3": None, "botocore": None, "botocore.exceptions": None}):
        with pytest.raises(CredentialError, match="boto3 is required"):
            AWSCredentialProvider().get_credentials("device-1")


def test_aws_returns_credentials():
    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    secret_data = {"ip": "10.2.2.2", "username": "admin", "password": "awspass"}
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps(secret_data)
    }
    mock_botocore = MagicMock()
    mock_botocore.exceptions.ClientError = Exception
    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore": mock_botocore, "botocore.exceptions": mock_botocore.exceptions}):
        creds = AWSCredentialProvider().get_credentials("slc9000-dc-b")
    assert creds == {"ip": "10.2.2.2", "username": "admin", "password": "awspass"}
    mock_client.get_secret_value.assert_called_once_with(SecretId="slc/slc9000-dc-b")


def test_aws_missing_secret_field_raises():
    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps({"ip": "10.2.2.2"})
    }
    mock_botocore = MagicMock()
    mock_botocore.exceptions.ClientError = Exception
    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore": mock_botocore, "botocore.exceptions": mock_botocore.exceptions}):
        with pytest.raises(CredentialError, match="missing field"):
            AWSCredentialProvider().get_credentials("device-1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_aws.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write providers/aws.py**

```python
import json

from slc_mcp.providers import CredentialProvider, CredentialError


class AWSCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError:
            raise CredentialError(
                "boto3 is required for the aws provider: pip install boto3"
            )
        secret_name = f"slc/{device_id}"
        sm_client = boto3.client("secretsmanager")
        try:
            response = sm_client.get_secret_value(SecretId=secret_name)
            data = json.loads(response["SecretString"])
        except ClientError as exc:
            raise CredentialError(
                f"AWS Secrets Manager read failed for {secret_name}: "
                f"{exc.response['Error']['Code']}"
            ) from exc
        except Exception as exc:
            raise CredentialError(
                f"AWS Secrets Manager error for {secret_name}: {exc}"
            ) from exc
        for field in ("ip", "username", "password"):
            if not data.get(field):
                raise CredentialError(
                    f"AWS secret {secret_name} missing field: {field!r}"
                )
        return {"ip": data["ip"], "username": data["username"], "password": data["password"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/providers/test_aws.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/slc_mcp/providers/aws.py tests/providers/test_aws.py
git commit -m "feat: AWSCredentialProvider (AWS Secrets Manager)"
```

---

### Task 13: Full test suite run

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -v`
Expected: PASS, all tests pass, 0 failures

- [ ] **Step 2: Fix any failures before continuing**

If any test fails, investigate and fix before moving to Task 14.

---

### Task 14: Integration tests with FakeSlcDevice

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write conftest.py with FakeSlcDevice fixture**

`tests/conftest.py`:

```python
import json
import pytest
from pytest_httpserver import HTTPServer


FAKE_TOKEN = "fake-integration-token-xyz"

FAKE_RESPONSES = {
    "/api/v2/system/status": {"status": "running", "uptime": 12345},
    "/api/v2/system/version": {"firmware": "9.7.0.0R10", "build": "12345"},
    "/api/v2/network/interfaces": {"interfaces": [{"name": "eth0", "ip": "10.0.0.1"}]},
    "/api/v2/system/ztp": {"enabled": False, "status": "complete"},
    "/api/v2/ports": {"ports": [{"id": 1, "label": "Port 1"}]},
    "/api/v2/ports/1/status": {"id": 1, "connected": True, "baud": 9600},
    "/api/v2/connections": {"connections": []},
    "/api/v2/managed_devices": {"devices": [{"id": "router-1"}]},
    "/api/v2/managed_devices/router-1/status": {"id": "router-1", "online": True},
    "/api/v2/cellular/status": {"modem": "present", "signal": -75},
    "/api/v2/firmware/version": {"version": "9.7.0.0R10"},
    "/api/v2/firmware/update_status": {"status": "idle"},
    "/api/v2/config/compare": {"diff": "none"},
}


@pytest.fixture(scope="session")
def fake_slc(httpserver: HTTPServer):
    # Login endpoint
    httpserver.expect_request(
        "/api/v2/user/login", method="POST"
    ).respond_with_json({"token": FAKE_TOKEN, "expires_in": 3600, "user": {"username": "admin"}})

    # GET endpoints
    for path, body in FAKE_RESPONSES.items():
        httpserver.expect_request(path, method="GET").respond_with_json(body)

    # POST endpoints
    httpserver.expect_request("/api/v2/firmware/check", method="POST").respond_with_json(
        {"status": "checking"}
    )
    httpserver.expect_request("/api/v2/config/save", method="POST").respond_with_json(
        {"status": 200, "code": "SUCCESS", "message": ["2 out of 2 total groups saved"]}
    )

    return httpserver
```

- [ ] **Step 2: Write integration tests**

`tests/test_integration.py`:

```python
import os
import pytest
from unittest.mock import patch

from tests.conftest import FAKE_TOKEN


@pytest.fixture(autouse=True)
def reset_sessions():
    """Clear session cache and force env provider before each test."""
    import slc_mcp.server as server
    server._sessions.clear_all()
    yield
    server._sessions.clear_all()


def _env_for(fake_slc) -> dict:
    host = f"127.0.0.1:{fake_slc.port}"
    return {
        "SLC_CREDENTIAL_PROVIDER": "env",
        "SLC_TESTDEV_IP": host,
        "SLC_TESTDEV_USERNAME": "admin",
        "SLC_TESTDEV_PASSWORD": "password",
        "SLC_VERIFY_SSL": "false",
        "SLC_API_PATH_PREFIX": "/api/v2",
    }


def test_get_system_status(fake_slc):
    import slc_mcp.server as server
    import slc_mcp.client as client
    with patch.object(client, "_VERIFY_SSL", False):
        with patch.dict(os.environ, _env_for(fake_slc), clear=False):
            from importlib import reload
            from slc_mcp.providers.env import EnvCredentialProvider
            server._sessions.set_provider(EnvCredentialProvider())
            result = server.get_system_status.__wrapped__("testdev")
    assert result["ok"] is True
    assert result["data"]["status"] == "running"


def test_get_slc_ports(fake_slc):
    import slc_mcp.server as server
    import slc_mcp.client as client
    with patch.object(client, "_VERIFY_SSL", False):
        with patch.dict(os.environ, _env_for(fake_slc), clear=False):
            server._sessions.set_provider(
                __import__("slc_mcp.providers.env", fromlist=["EnvCredentialProvider"]).EnvCredentialProvider()
            )
            result = server.get_slc_ports.__wrapped__("testdev")
    assert result["ok"] is True
    assert isinstance(result["data"]["ports"], list)


def test_save_config_without_confirm_blocked(fake_slc):
    import slc_mcp.server as server
    result = server.save_config.__wrapped__("testdev", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_save_config_with_confirm(fake_slc):
    import slc_mcp.server as server
    import slc_mcp.client as client
    with patch.object(client, "_VERIFY_SSL", False):
        with patch.dict(os.environ, _env_for(fake_slc), clear=False):
            server._sessions.set_provider(
                __import__("slc_mcp.providers.env", fromlist=["EnvCredentialProvider"]).EnvCredentialProvider()
            )
            result = server.save_config.__wrapped__("testdev", confirm=True)
    assert result["ok"] is True
    assert result["data"]["code"] == "SUCCESS"
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: PASS (4 tests)

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS, all tests, 0 failures

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_integration.py
git commit -m "test: FakeSlcDevice fixture and integration tests for all tool flows"
```

---

### Task 15: CLAUDE.md and config files

**Files:**
- Create: `CLAUDE.md`
- Create: `config/setup-instructions.md`
- Create: `config/claude_desktop_config.example.json`
- Create: `config/claude_desktop_config.wsl_windows.example.json`

- [ ] **Step 1: Create CLAUDE.md**

```markdown
# SLC MCP Server, Setup Guide

This repository provides a FastMCP server that exposes SLC9000 (and SLC8000/EMG)
device REST APIs as Claude tools. When you open this directory in Claude Code,
run the setup workflow below to configure your MCP client.

## Setup Workflow

1. Detect your platform: Mac, Linux, or Windows/WSL
2. Choose a credential provider: env (simplest), percepxion, vault, or aws
3. Collect the required env vars for your provider (see config/setup-instructions.md)
4. Find your Claude Desktop config file:
   - Mac/Linux: ~/Library/Application Support/Claude/claude_desktop_config.json
   - Windows: %APPDATA%\Claude\claude_desktop_config.json
   - WSL: /mnt/c/Users/<username>/AppData/Roaming/Claude/claude_desktop_config.json
5. Add the mcpServers block from config/claude_desktop_config.example.json
6. Restart Claude Desktop

## Verification

After restarting Claude Desktop, open a new conversation and ask:
"Use the get_system_status tool with device_id='your-device-id' to check my SLC device."

If the tool returns a 200 response with system data, the server is connected.

## Troubleshooting

- "Missing env vars": Check that your .env file has the correct SLC_* variables
- "Connection refused": Verify the device IP and that the device is reachable
- "Login failed": Verify credentials, default SLC admin password is on the device label
- SSL errors: The server uses verify=False by default for self-signed device certs

## Directory Structure

See docs/superpowers/specs/2026-05-19-slc-mcp-server-design.md for the full design.
```

- [ ] **Step 2: Create config/setup-instructions.md**

```markdown
# SLC MCP Server, Setup Instructions

## Prerequisites

- Python 3.11 or higher
- Network access to your SLC device(s) (HTTPS, port 443)
- Device admin credentials

## Step 1: Clone and Install

```bash
git clone https://github.com/keelhaulin/slc-mcp-server
cd slc-mcp-server
pip install -e .
```

## Step 2: Choose a Credential Provider

| Provider | Best for | Required env vars |
|----------|----------|-------------------|
| `env` | Single device or small fleet, credentials in .env | SLC_DEFAULT_IP, SLC_USERNAME, SLC_PASSWORD |
| `percepxion` | Fleet managed by Percepxion, IP from Percepxion, creds from env | PERCEPXION_API_URL, PERCEPXION_USERNAME, PERCEPXION_PASSWORD + SLC_USERNAME/PASSWORD |
| `vault` | HashiCorp Vault secret store | VAULT_ADDR, VAULT_TOKEN |
| `aws` | AWS Secrets Manager | AWS credential chain (env/IAM role/~/.aws/config) |

## Step 3: Set Environment Variables

Copy .env.example to .env and fill in your values:

```bash
cp .env.example .env
# Edit .env with your device credentials
```

## Step 4: Configure MCP Client

### Claude Desktop (Mac/Linux)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "slc-mcp-server": {
      "command": "python",
      "args": ["/absolute/path/to/slc-mcp-server/slc_mcp.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "SLC_CREDENTIAL_PROVIDER": "env",
        "SLC_DEFAULT_IP": "your-device-ip",
        "SLC_USERNAME": "admin",
        "SLC_PASSWORD": "yourpassword"
      }
    }
  }
}
```

### Claude Desktop (WSL/Windows)

See `config/claude_desktop_config.wsl_windows.example.json`.

## Step 5: Verify

Restart Claude Desktop. In a new conversation:

> "Call get_system_status with device_id='mydevice' and show me the result."

A successful response looks like:
```json
{"ok": true, "data": {"status": "running", "uptime": 86400}}
```
```

- [ ] **Step 3: Create config/claude_desktop_config.example.json**

```json
{
  "mcpServers": {
    "slc-mcp-server": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/slc-mcp-server/slc_mcp.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "SLC_CREDENTIAL_PROVIDER": "env",
        "SLC_DEFAULT_IP": "YOUR_DEVICE_IP",
        "SLC_USERNAME": "admin",
        "SLC_PASSWORD": "YOUR_PASSWORD",
        "SLC_VERIFY_SSL": "false",
        "SLC_REQUEST_TIMEOUT": "30"
      }
    }
  }
}
```

- [ ] **Step 4: Create config/claude_desktop_config.wsl_windows.example.json**

```json
{
  "mcpServers": {
    "slc-mcp-server": {
      "command": "wsl.exe",
      "args": [
        "bash",
        "-lc",
        "python /home/YOUR_WSL_USER/path/to/slc-mcp-server/slc_mcp.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "SLC_CREDENTIAL_PROVIDER": "env",
        "SLC_DEFAULT_IP": "YOUR_DEVICE_IP",
        "SLC_USERNAME": "admin",
        "SLC_PASSWORD": "YOUR_PASSWORD",
        "SLC_VERIFY_SSL": "false",
        "SLC_REQUEST_TIMEOUT": "30"
      }
    }
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md config/
git commit -m "docs: CLAUDE.md setup guide and config examples for all platforms"
```

---

### Task 16: Final validation

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass, 0 failures

- [ ] **Step 2: Verify server starts**

Run: `python slc_mcp.py &` (or `timeout 3 python slc_mcp.py; true`)
Expected: No import errors, FastMCP startup message to stderr

- [ ] **Step 3: Check all 16 tools are defined**

Run: `grep "@mcp.tool" src/slc_mcp/server.py | wc -l`
Expected: `16`

- [ ] **Step 4: Final commit with summary**

```bash
git add -A
git status
git commit -m "feat: slc-mcp-server v0.1.0, 16 tools, 4 credential providers, full test suite"
```
