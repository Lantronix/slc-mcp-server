# slc-mcp-server Developer Context

This file is auto-loaded when Claude Code opens this repo. Read before making changes.

## What This Is

FastMCP server exposing the Lantronix SLC 9000 REST API v2 as MCP tools. 33 tools covering ports, firmware, config, sessions, users, and network. Runs alongside `percepxion-mcp-server` — no overlap by design.

Local server code: `src/slc_mcp/`
Entry point: `run_server.py`
API spec: request the R21 spec from the PM-OS workspace at `reference-files/docs/SLC9000/API/SLC-API-v2-9_7_0_0R21-bundled.yaml`

## Naming Gotcha (CRITICAL)

Three independent namespaces exist for SLC devices. Do not confuse them.

| Name | CLI command | What it is | Who sees it |
|------|------------|------------|-------------|
| `hostname` | `set network host <name>` | OS-level network hostname | DNS, `get_system_identity` tool |
| `device_name` | `set px devicename <name>` | Percepxion registration name | Percepxion cloud, percepxion-mcp-server |
| `device_id` | (MCP param) | Identifier used by this server | MCP callers only |

These can all be different values on the same device. A device named `slc9000-dc-a` in Percepxion may have hostname `slc-raleigh-1` and be addressed as `dvt3` in the env vars. Never assume they match.

## Console Port SSH Formula

SSH port = `3000 + port_number`

Example: port 2 → TCP 3002. Lab DVT3 has a C3560G on port 2, accessible via TCP 3002.

Do NOT use 7001+N — that's Telnet, not SSH.

## Credential Providers

Five backends, selected by `SLC_CREDENTIAL_PROVIDER`:

| Provider | Good for | Key env vars |
|----------|----------|-------------|
| `env` | Lab/single device | `SLC_DEFAULT_IP`, `SLC_USERNAME`, `SLC_PASSWORD` |
| `percepxion` | IP lookup from Percepxion fleet | `PERCEPXION_API_URL`, `PERCEPXION_USERNAME`, `PERCEPXION_PASSWORD` |
| `vault` | HashiCorp Vault KV v2 | `VAULT_ADDR`, `VAULT_TOKEN` |
| `aws` | AWS Secrets Manager | Standard AWS credential chain |
| `cyberark` | CyberArk CCP (enterprise) | `CYBERARK_URL`, `CYBERARK_APP_ID`, `CYBERARK_SAFE` |

CyberArk mTLS: set `CYBERARK_CERT_PATH` + `CYBERARK_KEY_PATH` and it activates automatically. AppID-only is the default.

Key derivation for env provider: device_id `slc9000-dc-a` → key `SLC9000_DC_A` → env var `SLC_SLC9000_DC_A_IP`.

## R21 API Notes

Firmware R21 (9.7.0.0R21) vs R17: no new endpoints. Only doc/example cleanup in `/user/login` and a duplicate path parameter removed in `/ports/{ID}/action`. The 33 existing tools cover the full R21 API surface.

MQTT change (R21): `device_port.ports[]` wrapper removed; ports now at top-level as `ports[]`. This affects MQTT consumers (e.g. Percepxion's Mach10), not this MCP server's REST tools.

## Lab Devices

Never hard-code lab IPs or serials in server code. Use `.env` or a future SoT.

Lab addresses and credentials are in the PM-OS workspace `.env`. Ask for them via the PM-OS session if needed.

## Adding a New Tool

1. Add the FastMCP `@mcp.tool()` function to `server.py` using the appropriate `_call_get/post/put/patch/delete` helper
2. Destructive tools must require `confirm=True` (or a literal confirm string for irreversible ops)
3. All tools return `client._ok(data)` or `client._err(message)` — never raw exceptions
4. Add the tool to the Tool Reference table in `README.md`

## Testing

```bash
python3 -m pytest tests/ -v
```

No live device needed. Tests mock HTTP responses via `pytest-httpserver` and `responses`.

## Percepxion API Pairing

The `percepxion` credential provider calls `POST /v3/device/get` with `{"device_id": [device_id]}` and requires both `x-mystq-token` and `x-csrf-token` headers. Both are returned from the login response. See `src/slc_mcp/registry.py`.

The Percepxion API base URL is `https://api.percepxion.ai` (not `api.consoleflow.com` which is a legacy alias).
