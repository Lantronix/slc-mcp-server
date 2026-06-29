# Changelog

## [Unreleased]

### Added
- **Percepxion client tools**: four new tools for managing the Percepxion cloud client on an SLC device: `get_px_status`, `start_px_client`, `stop_px_client`, `restart_px_client`. Restart uses polling (`show px status` every 5s, default 120s timeout) because client shutdown takes 60-120 seconds. Write tools require `SLC_CLI_WRITE_ENABLED=true`; status is always readable.
- **CLI security policy** (`cli_policy.py`): server-side policy layer enforced before any CLI command reaches the device. Read-only by default (`SLC_CLI_WRITE_ENABLED=false`). Built-in deny list blocks destructive commands (`factory-reset`, `reload`, `reboot`, etc.). Configurable via `SLC_CLI_YOLO`, `SLC_CLI_MAX_LENGTH`, `SLC_CLI_DENY_COMMANDS`, `SLC_CLI_PERMIT_COMMANDS`. Policy applies to `apply_config_commands` and all px client write tools.
- **Docker instructions** in README: build and run commands, `.env` file usage, single-device env var example.
- **CLI Policy section** in README: documents all five env vars, built-in deny list, read-only default behavior, and the relationship to the SLC device's own role system.
- **CyberArk credential provider** (`providers/cyberark.py`): new fifth credential backend for enterprise deployments. Retrieves SLC device credentials from CyberArk Central Credential Provider (CCP) REST API. AppID-only by default; mTLS activates automatically when `CYBERARK_CERT_PATH` and `CYBERARK_KEY_PATH` are set. Device IP pulled from the CyberArk account's Address field, with fallback to `SLC_{KEY}_IP` env vars.
- **CLAUDE.md**: developer context file for Claude Code sessions, documents naming gotchas, port formula, provider guide, and R21 API notes.
- **Dockerfile**: containerized deployment support.
- **LICENSE**: MIT license.

### Fixed
- **`apply_config_commands` critical bug**: the `/config/batch` endpoint requires `commands` as a newline-delimited string, not a JSON array. Every prior call sent `{"commands": [...]}` and received `INVALID_JSON` from the device. Fixed to `{"commands": "\n".join(commands)}`.
- **`client.py` auth error messages**: `login()` now distinguishes 401 (invalid credentials), 403 (account locked or insufficient permissions), and 503 (auth service unavailable) instead of a generic HTTP status message. All five HTTP methods similarly distinguish 401 (session expired / invalid credentials) from 403 (insufficient permissions for the operation) with actionable error text.
- **README prerequisites**: removed the requirement for "sysadmin account", any account with permissions appropriate for the requested operations works.
- `registry.py`: corrected Percepxion device lookup from `GET /v3/device/get?id=` to `POST /v3/device/get` with JSON body `{"device_id": [device_id]}`. The old GET form was unsupported by the current Percepxion API and silently returned 404.
- `registry.py`: login now stores and uses both `x-mystq-token` and `x-csrf-token`. The old implementation discarded `csrf_token`, causing 403s on subsequent device lookups.
- `.env.example`: updated `PERCEPXION_API_URL` default from `https://api.consoleflow.com` (legacy alias) to `https://api.percepxion.ai`.
- `configure_provider` tool: `cyberark` added to the valid provider list.
- `README.md`: updated percepxion-mcp-server link to `Lantronix/percepxion-mcp-server`.

### Changed
- R21 API (9.7.0.0R21) review complete. No new endpoints vs R17. Two minor spec clarifications in `/user/login` (example type corrections) and `/ports/{ID}/action` (duplicate path parameter removed). No tool changes required.

## [0.1.0], initial release

- 33 MCP tools covering the SLC 9000 REST API v2: sessions, system, network, ports, managed devices, cellular, firmware, config management, users
- Credential providers: env, percepxion, vault, aws
- 2FA support: automatic TOTP challenge-response via `pyotp`
- Integration test suite with mocked HTTP (no live device required)
