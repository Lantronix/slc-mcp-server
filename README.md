# slc-mcp-server

An MCP (Model Context Protocol) server that exposes the Lantronix SLC9000 console server REST API as tools for AI agents. Agents can query port status, manage firmware, apply configuration, and control device sessions without touching the web UI or writing curl commands.

This server handles device-level operations against individual SLC9000 units. It's designed to work alongside [percepxion-mcp-server](https://github.com/Lantronix/percepxion-mcp-server), which handles fleet-level operations through the Percepxion cloud platform. There's no capability overlap by design: when both servers are configured, the agent routes device-specific calls here and fleet-wide calls to Percepxion.

## Capability Split

| Capability | slc-mcp-server | percepxion-mcp-server |
|---|---|---|
| Serial port status/config | `get_slc_port`, `get_slc_ports` | `list_device_ports` |
| CLI commands, sync output (single call) | `apply_config_commands` |, |
| CLI commands, async output (job + fetch) |, | `send_direct_cli_command` + `get_cli_command_output` |
| Firmware update | `firmware_update`, `get_firmware_update_status` | `update_firmware_by_smart_group` |
| Device config backup | `export_config_commands` | `get_device_config` |
| User/session management | `get_sessions`, `terminate_session` |, |
| Reboot | `reboot_device` | `reboot_device` (fleet) |
| Cellular status | `get_cellular_status` |, |
| Fleet-wide ops |, | smart groups, templates |
| Audit logs |, | `investigate_audit_logs` |

## Prerequisites

- Python 3.11+
- Network access to the SLC9000 device (direct IP or via jump host)
- Device credentials with permissions appropriate for the operations requested. The SLC's built-in authentication and role system applies: read-only accounts can use read-only tools, and the server returns informative errors when credentials are invalid or lack the permissions needed for a given operation.

```bash
pip install -e .
```

This installs all dependencies including `pyotp`, which is required for 2FA-enabled devices.

## Configuration

Set environment variables before starting the server, or put them in a `.env` file in the project root.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SLC_DEFAULT_IP` |, | Default device IP, used when device_id isn't in the registry |
| `SLC_USERNAME` | `sysadmin` | Default username |
| `SLC_PASSWORD` |, | Default password |
| `SLC_TOTP_SECRET` |, | Default TOTP secret for 2FA-enabled devices |
| `SLC_{KEY}_IP` |, | Per-device IP where KEY is the device identifier (uppercased, non-alphanumeric replaced with `_`) |
| `SLC_{KEY}_USERNAME` |, | Per-device username |
| `SLC_{KEY}_PASSWORD` |, | Per-device password |
| `SLC_{KEY}_TOTP_SECRET` |, | Per-device TOTP secret |
| `SLC_VERIFY_SSL` | `true` | Set to `false` only for lab devices with self-signed certificates. Never disable in production. |
| `SLC_CREDENTIAL_PROVIDER` | `env` | Credential backend: `env`, `vault`, `aws`, `percepxion`, `cyberark` |
| `SLC_KNOWN_DEVICE_IDS` | unset | `env` provider only. Comma-separated allow-list of device_ids. When set, rejects any device_id not in this list before attempting the default-credential fallback. Opt-in; leave unset for the default single-device lab workflow below. |

**Key derivation example:** device_id `slc9000-dc-a` becomes key `SLC9000_DC_A`, so the IP var is `SLC_SLC9000_DC_A_IP`.

### Minimal .env

```bash
SLC_DEFAULT_IP=192.168.100.76
SLC_USERNAME=sysadmin
SLC_PASSWORD=yourpassword
SLC_VERIFY_SSL=false
```

## Docker

Build and run the server in a container. All configuration passes via environment variables or a `.env` file.

**Build:**

```bash
docker build -t slc-mcp-server .
```

**Run with a `.env` file:**

```bash
docker run --rm --env-file .env slc-mcp-server
```

**Run with individual env vars (single device, lab):**

```bash
docker run --rm \
  -e SLC_DEFAULT_IP=192.168.100.76 \
  -e SLC_USERNAME=sysadmin \
  -e SLC_PASSWORD=yourpassword \
  -e SLC_VERIFY_SSL=false \
  slc-mcp-server
```

For production deployments with HashiCorp Vault or CyberArk, pass the relevant env vars instead of embedding credentials in the image. The Dockerfile uses a non-root user by default.

## CLI Policy

The server enforces a CLI policy layer on top of the SLC device's own permission system. By default, `apply_config_commands` and the Percepxion client write tools (`start_px_client`, `stop_px_client`, `restart_px_client`) reject write commands unless explicitly enabled.

| Variable | Default | Description |
|---|---|---|
| `SLC_CLI_WRITE_ENABLED` | `false` | Allow write commands via `apply_config_commands` and px client tools |
| `SLC_CLI_YOLO` | `false` | Disable all CLI policy filtering. Never use in production. |
| `SLC_CLI_MAX_LENGTH` | `512` | Maximum command length in characters |
| `SLC_CLI_DENY_COMMANDS` | built-in list | Comma-separated additional commands to block |
| `SLC_CLI_PERMIT_COMMANDS` | unset | Comma-separated allowlist, if set, only these prefixes are permitted |

**Built-in deny list** (always blocked unless `SLC_CLI_YOLO=true`): `factory-reset`, `write erase`, `erase startup-config`, `erase flash`, `reload`, `reboot`, `format`, `shutdown`, `power off`, `reset system`, `init 0`, `halt`.

Read-only commands (`show`, `diag`, `ping`, `traceroute`, etc.) are always permitted regardless of `SLC_CLI_WRITE_ENABLED`. The `get_px_status` tool is always permitted.

This policy layer sits in addition to the SLC device's own user role restrictions. A command that passes the MCP policy layer can still be rejected by the device if the configured account lacks the required role.

## Credential Providers

**env (default):** Reads credentials from environment variables as described above. Per-device vars take priority over globals. Good for single-device or small lab setups.

**vault:** Reads from HashiCorp Vault KV v2 at path `slc/{device_id}`. Requires `VAULT_ADDR` and `VAULT_TOKEN` env vars. The Vault secret must contain `ip`, `username`, `password`, and optionally `totp_secret`. Good for production deployments where secrets are already in Vault.

**aws:** Reads from AWS Secrets Manager at secret name `slc/{device_id}`. Requires standard AWS credential configuration (IAM role, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, or instance profile). Secret JSON must contain `ip`, `username`, `password`, and optionally `totp_secret`.

**percepxion:** Looks up the device IP from the Percepxion device registry by device_id, using the Percepxion API. Requires `PERCEPXION_API_URL` (default `https://api.percepxion.ai`), `PERCEPXION_USERNAME`, `PERCEPXION_PASSWORD`. SLC credentials still come from `SLC_{KEY}_*` env vars. Use this when your device inventory is managed in Percepxion and IPs change.

**cyberark:** Retrieves credentials from CyberArk Central Credential Provider (CCP) REST API. Requires `CYBERARK_URL`, `CYBERARK_APP_ID`, `CYBERARK_SAFE`. Each SLC device must have an account stored in CyberArk with Object = device_id and Address = management IP. When `CYBERARK_CERT_PATH` and `CYBERARK_KEY_PATH` are set, mTLS is enabled automatically. See `.env.example` for all options.

Switch providers at runtime without restarting:

```
configure_provider("vault")
```

## 2FA Support

When a device has 2FA enabled with TOTP (time-based one-time passwords), the server handles the challenge-response flow automatically. The login endpoint returns a challenge, the server generates the current TOTP code, and submits it in a second request.

To configure this, generate a TOTP secret on the device web UI and set the corresponding env var:

```bash
SLC_MYDEVICE_TOTP_SECRET=JBSWY3DPEHPK3PXP
```

The value is the base32 secret string, not a numeric code. PIN setup challenges (first-time 2FA activation where the device asks you to set a PIN) must be completed through the device web UI before the MCP server can authenticate. Only TOTP (`passcode`/`tokencode` challenge types) are handled automatically.

## CLI Command Routing

Two tools handle CLI commands and they behave differently. Pick based on reachability and whether synchronous output is worth the trade-off against fleet-wide dispatch.

`apply_config_commands` (this server, `POST /config/batch`) sends CLI configuration commands to the SLC device and returns synchronous output directly, in one call, no polling. Use this when you have direct network access to the device and want output immediately.

`send_direct_cli_command` (percepxion-mcp-server) dispatches CLI commands through Percepxion's async job system, useful for devices reachable only through Percepxion (no direct network path) or for fleet-wide dispatch. Output is retrievable, but not synchronously: poll `search_job_groups`/`get_job_group` until status reaches `"Completed"`, then call `get_cli_command_output` (percepxion-mcp-server v1.1.0+) for the actual device response text. Before v1.1.0, only job status was reachable via the API at all, output text was believed unreachable; that's no longer the case, `get_cli_command_output` calls the same endpoint Percepxion's own WebUI console-editor uses to render command output.

When both servers are configured: prefer `apply_config_commands` for a directly-reachable device where you want output in one call with no polling. Use `send_direct_cli_command` + `get_cli_command_output` for devices without direct network access, or for fleet-wide/bulk dispatch where the extra async round trip is an acceptable trade-off.

## Tool Reference

### Auth & Sessions

| Tool | Description |
|---|---|
| `logout_device(device_id)` | Invalidate the current API session token |
| `get_sessions(device_id)` | List all active sessions (web UI, API, WebTerm) |
| `get_session(device_id, session_id)` | Get details for a specific session |
| `terminate_session(device_id, session_id, confirm=True)` | Forcibly terminate a session |

### System

| Tool | Description |
|---|---|
| `get_system_status(device_id)` | System status (uptime, state, etc.) |
| `get_system_version(device_id)` | Firmware and software version |
| `get_system_identity(device_id)` | Hostname, description, contact, location |
| `update_system_identity(device_id, hostname, description, confirm=True)` | Update hostname or description |
| `get_ztp_status(device_id)` | Zero Touch Provisioning status |
| `reboot_device(device_id, confirm=True)` | Reboot the device |

### Network

| Tool | Description |
|---|---|
| `get_network_interfaces(device_id)` | All interface configurations and status |

### Ports & Connections

| Tool | Description |
|---|---|
| `get_slc_ports(device_id)` | All serial port configurations and status |
| `get_slc_port(device_id, port_id)` | Single port status (`port_id` is a string like `"1"`) |
| `get_connections(device_id)` | All active connections |
| `get_managed_devices(device_id)` | Inventory of managed devices |
| `get_managed_device(device_id, managed_device_id)` | Single managed device status |
| `get_cellular_status(device_id)` | Cellular modem status (firmware_revision, signal_strength, imei, iccid, model, band, apn, state) |

### Firmware

| Tool | Description |
|---|---|
| `get_firmware_version(device_id)` | Installed firmware version |
| `get_firmware_update_status(device_id)` | Status of in-progress or completed update |
| `check_firmware_updates(device_id)` | Check for available updates |
| `get_firmware_bootbank(device_id)` | Active boot bank (1 or 2) |
| `set_firmware_bootbank(device_id, bank, confirm=True)` | Set boot bank for next reboot |
| `firmware_update(device_id, preserveconfig=True, confirm=True)` | Trigger firmware update |
| `get_firmware_log(device_id)` | Log from the most recent update |

### Config Management

| Tool | Description |
|---|---|
| `save_config(device_id, confirm=True)` | Save running config to non-volatile storage |
| `export_config_commands(device_id)` | Export config as replayable CLI commands |
| `apply_config_commands(device_id, commands, confirm=True)` | Apply CLI config commands, returns output. Read-only by default (`SLC_CLI_WRITE_ENABLED=false`). |
| `restore_config_baseline(device_id, confirm=True)` | Restore saved baseline config |
| `export_config_for_edit(device_id)` | Export full config blob for editing |
| `factory_reset(device_id, confirm="FACTORY RESET")` | Reset to factory defaults (irreversible) |

### Users

| Tool | Description |
|---|---|
| `get_sysadmin_user(device_id)` | Sysadmin account configuration |
| `update_sysadmin_user(device_id, new_password, allow_dialback, dialback_number, confirm=True)` | Update sysadmin settings |

### Percepxion Client

Tools for managing the Percepxion cloud client running on the SLC device. Status is always readable; start/stop/restart require `SLC_CLI_WRITE_ENABLED=true`.

| Tool | Description |
|---|---|
| `get_px_status(device_id)` | Percepxion client status: enable state, connection, server URL, last heartbeat |
| `start_px_client(device_id, confirm=True)` | Enable the Percepxion client (registers with cloud in ~30s) |
| `stop_px_client(device_id, confirm=True)` | Disable the Percepxion client (shutdown takes 60-120s) |
| `restart_px_client(device_id, confirm=True, timeout_seconds=120)` | Disable, wait for stopped state, then enable |

### Admin

| Tool | Description |
|---|---|
| `configure_provider(provider)` | Switch credential provider (env, vault, aws, percepxion, cyberark) |

## Multi-Server Claude Desktop Config

Configure both servers together for full device + fleet coverage:

```json
{
  "mcpServers": {
    "slc-mcp-server": {
      "command": "python3",
      "args": ["/path/to/slc-mcp-server/run_server.py"],
      "env": {
        "SLC_DEFAULT_IP": "192.168.100.76",
        "SLC_USERNAME": "sysadmin",
        "SLC_PASSWORD": "yourpassword",
        "SLC_VERIFY_SSL": "false"
      }
    },
    "percepxion-mcp-server": {
      "command": "python3",
      "args": ["/path/to/percepxion-mcp-server/percepxion_mcp.py"],
      "env": {
        "PERCEPXION_API_URL": "https://api.percepxion.ai/api",
        "PERCEPXION_USERNAME": "user@example.com",
        "PERCEPXION_PASSWORD": "yourpassword"
      }
    }
  }
}
```

## Claude Skill

[`skills/slc-device-ops/SKILL.md`](skills/slc-device-ops/SKILL.md) packages the operational knowledge for this server: sync-vs-async CLI routing, credential provider setup, confirm-before-write discipline, and the standard workflows (health check, port inspection, config backup/apply, firmware with boot banks, sessions, Percepxion client control). With the skill installed, Claude uses the tools correctly on the first try instead of rediscovering these patterns.

Install for all your projects:

```bash
mkdir -p ~/.claude/skills && cp -r skills/slc-device-ops ~/.claude/skills/
```

Or copy into a single project's `.claude/skills/` directory. The same file can be uploaded to claude.ai as a skill. Keep the skill in sync when tools change: `tests/test_skill_doc.py` fails the suite if tool names drift.

## Testing

```bash
cd /path/to/slc-mcp-server
python3 -m pytest tests/ -v
```

The test suite covers all 33 tools including confirm guards, 2FA challenge flows, error body parsing, and new HTTP methods (PUT, DELETE, PATCH). No live device is required; tests use mocked HTTP responses.
