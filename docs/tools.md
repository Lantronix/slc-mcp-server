# SLC MCP Server, Tool Reference

37 tools covering the SLC 9000 REST API v2. API base path: `/api/v2`. Authoritative spec: `SLC-API-v2-9_7_0_0R21-bundled.yaml`.

All tools return `{"ok": true, "data": {...}}` on success or `{"ok": false, "error": "..."}` on failure.

## Admin

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `configure_provider` | Switch active credential provider and clear session cache. Providers: `env`, `percepxion`, `vault`, `aws`, `cyberark`. |, |

## Auth & Sessions

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `logout_device` | Invalidate the current API session token. | `DELETE /user/login` |
| `get_sessions` | List all active sessions (web UI, API, WebTerm). | `GET /sessions` |
| `get_session` | Get details for a specific active session. | `GET /sessions/{session_id}` |
| `terminate_session` | Forcibly terminate an active session. Requires `confirm=True`. | `DELETE /sessions/{session_id}` |

## System

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_system_status` | Get system health and status. | `GET /system/status` |
| `get_system_version` | Get firmware and software versions. | `GET /system/version` |
| `get_system_identity` | Get hostname, description, contact, location. | `GET /system/identity` |
| `update_system_identity` | Update hostname or description. Requires `confirm=True`. | `POST /system/identity` |
| `reboot_device` | Reboot the device. Requires `confirm=True`. Returns 400 if a firmware update is in progress. | `POST /system/reboot` |
| `get_ztp_status` | Get Zero Touch Provisioning status. | `GET /system/ztp` |

## Network

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_network_interfaces` | Get all interface configurations and status. | `GET /network/interfaces` |

## Ports & Connections

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_slc_ports` | Get all serial port configurations and status. | `GET /ports` |
| `get_slc_port` | Get status for a single serial port. `port_id` is the port number as a string (e.g. `"1"`). | `GET /ports/{port_id}/status` |
| `get_connections` | Get all active connections. | `GET /connections` |
| `get_managed_devices` | Get inventory of all managed devices. | `GET /managed_devices` |
| `get_managed_device` | Get status of a single managed device. | `GET /managed_devices/{managed_device_id}/status` |

## Cellular

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_cellular_status` | Get modem status: signal, IMEI, ICCID, APN, band, roaming, uptime. | `GET /cellular/status` |

## Firmware

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_firmware_version` | Get installed firmware version. | `GET /firmware/version` |
| `get_firmware_update_status` | Get status of in-progress or completed update. | `GET /firmware/update_status` |
| `check_firmware_updates` | Check for available firmware updates. | `GET /firmware/check` |
| `get_firmware_bootbank` | Get active boot bank (1 or 2). | `GET /firmware/bootbank` |
| `set_firmware_bootbank` | Set boot bank for next reboot. Requires `confirm=True`. | `PUT /firmware/bootbank` |
| `firmware_update` | Trigger a firmware update. Requires `confirm=True`. Monitor with `get_firmware_update_status`. | `POST /firmware/update` |
| `get_firmware_log` | Get log from the most recent firmware update. | `GET /firmware/log` |

## Config Management

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `save_config` | Save running config to non-volatile storage. Requires `confirm=True`. | `POST /config/save` |
| `export_config_commands` | Export config as a list of replayable CLI commands. Useful for backup and drift detection. | `GET /config/commands` |
| `apply_config_commands` | Apply a list of CLI commands synchronously. Returns command output. Requires `confirm=True`. Commands pass through CLI policy before sending, read-only by default (`SLC_CLI_WRITE_ENABLED=false`). | `POST /config/batch` |
| `restore_config_baseline` | Restore the saved baseline config. Requires `confirm=True`. Returns 404 if no baseline exists. | `POST /config/baseline` |
| `export_config_for_edit` | Export raw config blob for editing. | `POST /config/edit` |
| `factory_reset` | Reset to factory defaults. Pass `confirm='FACTORY RESET'` (exact string). Irreversible. | `POST /config/factory_reset` |

## Users

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_sysadmin_user` | Get sysadmin account config (password policy, dialback settings). | `GET /users/sysadmin` |
| `update_sysadmin_user` | Update sysadmin password, dialback settings. Requires `confirm=True`. | `PATCH /users/sysadmin` |

## Percepxion Client

These tools manage the Percepxion cloud client running on the SLC device. They route through `POST /config/batch` (CLI commands) since no REST endpoint exists for px client management. Status is always readable; write tools require `SLC_CLI_WRITE_ENABLED=true`.

| Tool | Description | API endpoint |
|------|-------------|--------------|
| `get_px_status` | Get Percepxion client status: enable state, connection, server URL, heartbeat. Always permitted. | `POST /config/batch` (`show px status`) |
| `start_px_client` | Enable the Percepxion client. Client registers with cloud in ~30s. Requires `confirm=True`. | `POST /config/batch` (`set px client enable`) |
| `stop_px_client` | Disable the Percepxion client. Shutdown takes 60-120s. Requires `confirm=True`. | `POST /config/batch` (`set px client disable`) |
| `restart_px_client` | Disable, poll until stopped (default 120s timeout), then enable. Requires `confirm=True`. | `POST /config/batch` |

## Destructive Operation Safety

Tools that modify or delete device state require one of:
- `confirm=True`, boolean flag for reversible operations
- `confirm='EXACT STRING'`, literal string for irreversible operations (factory reset)

This is a deliberate design choice. Don't remove the guards.
