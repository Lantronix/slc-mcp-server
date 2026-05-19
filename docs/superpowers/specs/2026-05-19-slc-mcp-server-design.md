# SLC MCP Server, Design Spec

**Date:** 2026-05-19
**Status:** Approved
**Repo:** https://github.com/keelhaulin/slc-mcp-server

---

## Overview

A Python FastMCP server that exposes the SLC9000 (and SLC8000/EMG) device REST API as MCP tools. Connects to devices directly over HTTPS using per-device credentials fetched JIT from a pluggable credential provider. Percepxion is used as the authoritative device registry (resolving `device_id` → IP), but is not required as the credential store, operators can use env vars, HashiCorp Vault, or AWS Secrets Manager instead.

This design is intentionally parallel to the Percepxion MCP Server in structure, security practices, and response envelope, so the two servers compose naturally in the same Claude session.

---

## Goals

- Expose SLC device API capabilities not available through Percepxion (per-port serial status, managed device inventory, active connections, cellular health, config drift)
- Support four credential providers in v1: env, Percepxion, HashiCorp Vault, AWS Secrets Manager
- Cache per-device auth tokens for the process lifetime; re-authenticate transparently on 401
- Never log or expose credential values at any level
- Provide LLM-guided setup so new users can configure their MCP client without manual JSON editing

---

## Non-Goals (v1)

- `/config/edit` (requires device schema knowledge, separate design pass)
- `/system/reboot`, `/config/factory_reset`, `/users/sysadmin` (destructive, excluded)
- Inter-server MCP communication (Percepxion MCP and SLC MCP are independent servers; Claude orchestrates both)
- CyberArk / Delinea / Azure Key Vault providers (stubs welcomed, full implementation deferred)

---

## Architecture

### Module structure

```
slc-mcp-server/
├── src/slc_mcp/
│   ├── __init__.py
│   ├── server.py           # FastMCP instance + all @mcp.tool() definitions
│   ├── client.py           # SLC device REST client (_get, _post, _ok, _err)
│   ├── session.py          # Per-device session cache (device_id → token)
│   ├── registry.py         # DeviceRegistry: resolves device_id → ip via Percepxion
│   └── providers/
│       ├── __init__.py     # CredentialProvider ABC + get_provider() factory
│       ├── env.py          # EnvCredentialProvider
│       ├── percepxion.py   # PercepxionCredentialProvider
│       ├── vault.py        # VaultCredentialProvider (hvac)
│       └── aws.py          # AWSCredentialProvider (boto3)
├── slc_mcp.py              # Entry point
├── pyproject.toml
├── requirements.txt
├── .env.example
├── CLAUDE.md               # LLM-readable setup guide for Claude Code users
└── config/
    ├── setup-instructions.md                       # LLM-readable setup for any client
    ├── claude_desktop_config.example.json          # Mac/Linux reference
    └── claude_desktop_config.wsl_windows.example.json  # WSL/Windows reference
```

### Request flow

```
Claude calls get_slc_ports(device_id="slc9000-dc-a")
    │
    ▼
server.py tool handler
    │
    ▼
session.get_or_create("slc9000-dc-a")
    ├── Cache hit → return existing DeviceSession
    └── Cache miss →
            provider.get_credentials("slc9000-dc-a")
                └── Returns {ip, username, password}  [from env / Percepxion / Vault / AWS]
            client.login(ip, username, password)
                └── POST /api/v2/user/login → Bearer token
            Store DeviceSession(ip, token)
    │
    ▼
client.get(session, "/api/v2/ports")
    │
    ▼
_ok(data) or _err(message)  ← same envelope as Percepxion MCP
```

---

## Credential Providers

### Interface

```python
class CredentialProvider(ABC):
    @abstractmethod
    def get_credentials(self, device_id: str) -> dict[str, str]:
        """Return {"ip": ..., "username": ..., "password": ...}.
        Raise CredentialError if device_id is unknown or creds are missing."""
```

Provider is selected by `SLC_CREDENTIAL_PROVIDER` env var at startup. Valid values: `env`, `percepxion`, `vault`, `aws`. Default: `env`.

### EnvCredentialProvider

Reads per-device env vars:
- `SLC_{DEVICE_ID}_IP`
- `SLC_{DEVICE_ID}_USERNAME`
- `SLC_{DEVICE_ID}_PASSWORD`

Falls back to global defaults for single-device setups:
- `SLC_DEFAULT_IP`
- `SLC_USERNAME`
- `SLC_PASSWORD`

`DEVICE_ID` is uppercased and non-alphanumeric characters replaced with `_`.

### PercepxionCredentialProvider

Uses Percepxion as the device registry only (IP resolution via `/v3/device/get`). Credentials still come from per-device env vars. Requires Percepxion session env vars (`PERCEPXION_API_URL`, `PERCEPXION_USERNAME`, `PERCEPXION_PASSWORD`).

### VaultCredentialProvider

Reads `secret/slc/{device_id}` from HashiCorp Vault KV v2. Expected secret keys: `ip`, `username`, `password`. Auth via `VAULT_ADDR` + `VAULT_TOKEN`. Uses `hvac` library.

### AWSCredentialProvider

Reads secret named `slc/{device_id}` from AWS Secrets Manager. Expected JSON keys: `ip`, `username`, `password`. Auth via standard AWS credential chain (env vars, IAM role, `~/.aws/config`). Uses `boto3`.

---

## Session Management

`session.py` maintains a `dict[str, DeviceSession]` keyed by `device_id`.

```python
@dataclass
class DeviceSession:
    ip: str
    token: str
    valid: bool = True
```

`get_or_create(device_id)` returns a live session, authenticating if the cache misses. On 401 from any API call, the client calls `session.invalidate(device_id)` and returns `_err(..., 401)`. The next tool call for that device re-authenticates automatically.

Session state is process-scoped. Restarting the server clears all sessions.

---

## SLC API Client

`client.py` wraps all HTTP calls to device REST APIs. Enforces:

- Bearer token auth on every request (`Authorization: Bearer {token}`)
- `Content-Type: application/json` on POST
- Configurable timeout via `SLC_REQUEST_TIMEOUT` (default 30s)
- Consistent `_ok/_err` response envelope

Methods:
- `_get(session, path)` → `_ok/_err`
- `_post(session, path, json_body)` → `_ok/_err`
- `login(ip, username, password)` → `str` (token) or raises `AuthError`

The client never logs credential values. Connection errors produce `_err` with the device IP and error type, no stack trace.

---

## Tool Inventory

All tools accept `device_id: str` as the first parameter. All return `{"ok": bool, "data": {...}}` or `{"ok": false, "error": "..."}`.

| Tool | SLC Endpoint | Method |
|---|---|---|
| `configure_provider` | n/a | n/a |
| `get_system_status` | `/system/status` | GET |
| `get_system_version` | `/system/version` | GET |
| `get_network_interfaces` | `/network/interfaces` | GET |
| `get_ztp_status` | `/system/ztp` | GET |
| `get_slc_ports` | `/ports` | GET |
| `get_slc_port` | `/ports/{id}` | GET |
| `get_connections` | `/connections` | GET |
| `get_managed_devices` | `/managed_devices` | GET |
| `get_managed_device` | `/managed_devices/{id}` | GET |
| `get_cellular_status` | `/cellular/status` | GET |
| `get_firmware_version` | `/firmware/version` | GET |
| `get_firmware_update_status` | `/firmware/update_status` | GET |
| `check_firmware_updates` | `/firmware/check` | POST |
| `compare_config` | `/config/compare` | GET |
| `save_config` | `/config/save` | POST |

`configure_provider` takes no `device_id`. It accepts a `provider` argument (`env` | `percepxion` | `vault` | `aws`) and switches the active provider for the session, clearing all cached device sessions.

---

## Error Handling

All tools catch all exceptions and return `_err`. No exceptions propagate to the MCP layer.

| Condition | Response |
|---|---|
| 401 from device | `_err("Session expired, retry to re-authenticate.", 401)` + session invalidated |
| `CredentialError` | `_err` naming the missing env var or secret path, never the value |
| Connection timeout | `_err` with device IP and "Connection timed out" |
| Connection refused | `_err` with device IP and "Connection refused, is the device reachable?" |
| Any other HTTP error | `_err` with status code and sanitized body |

---

## Security Practices

Carried forward from Percepxion MCP Server and extended for multi-device:

- Credentials sourced exclusively from env vars or external secret stores, never hardcoded, never in tool parameters
- Tokens stored in process memory only, never written to disk, never logged
- All logging to `stderr` (MCP wire is `stdout`)
- `PYTHONUNBUFFERED=1` in all Claude Desktop example configs
- Request timeout enforced on every HTTP call
- `require_auth` guard on every tool that contacts a device
- Provider never logs credential values at any log level, including DEBUG
- `_err` responses never echo credential content, even partially
- Per-device session isolation: token for device A is never used for device B
- JIT fetch: provider is called only on cache miss, credentials are not retained in the provider object after `get_credentials()` returns

---

## LLM-Guided Setup

### `CLAUDE.md` (repo root)

Claude Code reads this automatically when a user opens the cloned directory. Contains an instruction block directing Claude to run a setup workflow:

1. Detect platform (Mac, Linux, WSL/Windows)
2. Ask which credential provider the user is configuring
3. Prompt for provider-specific env vars
4. Ask for the repo path on their machine
5. Locate the user's Claude config file
6. Write the correct `mcpServers` block
7. Verify the entry and show next steps

### `config/setup-instructions.md`

Structured for any LLM client. Covers:
- Prerequisites (Python 3.11+, network access to devices)
- Provider selection decision tree
- Per-provider required env vars
- Claude config file paths by platform
- Verification steps (how to confirm the server connected)

### Static example configs

- `config/claude_desktop_config.example.json`, Mac/Linux
- `config/claude_desktop_config.wsl_windows.example.json`, WSL/Windows

---

## Dependencies

```
fastmcp
requests
python-dotenv
hvac          # Vault provider
boto3         # AWS provider
```

`hvac` and `boto3` are optional at runtime, import errors are caught and surfaced only when the relevant provider is selected.

---

## Testing approach

- Unit tests for each provider using mocked HTTP (no live device or secret store required)
- Unit tests for session manager: cache hit, cache miss, 401 invalidation, re-auth
- Unit tests for client: `_ok/_err` envelope, timeout handling, 401 path
- Integration test fixture: a `FakeSlcDevice` HTTP server (using `pytest-httpserver`) that serves static JSON for the 16 endpoints, lets full tool call flows run without a real SLC device
- No tests require live Vault, AWS, or Percepxion, all external calls are mockable at the provider interface

---

## Open Questions (deferred)

- Should `save_config` require a confirmation parameter to prevent accidental writes? (Lean yes, add `confirm: bool = False` guard)
- Stub implementations for CyberArk / Azure Key Vault, ship as `NotImplementedError` with a docstring pointing to the provider interface?
- Should the server expose a `list_cached_sessions` diagnostic tool for operators?
