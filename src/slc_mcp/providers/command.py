import json
import os
import re
import shlex
import subprocess

from slc_mcp.providers import CredentialError, CredentialProvider

_PLACEHOLDER = "{device_id}"
_SAFE_DEVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_STDERR_LIMIT = 200


class CommandCredentialProvider(CredentialProvider):
    """Run an operator-configured command to fetch one device's credentials.

    Works with any secrets tool that has a CLI (1Password ``op``, Bitwarden
    ``bws``, Infisical, Delinea, Keeper, in-house scripts).

    Env vars:
        SLC_CREDENTIAL_COMMAND          Command line to run. Split with shlex and
                                        run without a shell. Every ``{device_id}``
                                        in it is replaced with the device_id. The
                                        child also gets SLC_DEVICE_ID in its env.
        SLC_CREDENTIAL_COMMAND_TIMEOUT  Seconds before the command is killed
                                        (default 30).
        SLC_KNOWN_DEVICE_IDS            Optional allow-list, checked before the
                                        command runs.

    The command prints a JSON object with ``ip``, ``username``, ``password``
    and optionally ``totp_secret``. It comes only from the server's environment;
    no tool argument can set or change it. Command output never appears in
    error messages.
    """

    def __init__(self) -> None:
        raw = (os.getenv("SLC_CREDENTIAL_COMMAND") or "").strip()
        if not raw:
            raise CredentialError(
                "SLC_CREDENTIAL_COMMAND must be set when using the 'command' provider."
            )
        self._argv = shlex.split(raw, posix=os.name != "nt")
        timeout_raw = os.getenv("SLC_CREDENTIAL_COMMAND_TIMEOUT", "30")
        try:
            self._timeout = float(timeout_raw)
        except ValueError as exc:
            raise CredentialError(
                f"SLC_CREDENTIAL_COMMAND_TIMEOUT must be a number, got {timeout_raw!r}"
            ) from exc
        if self._timeout <= 0:
            raise CredentialError("SLC_CREDENTIAL_COMMAND_TIMEOUT must be greater than 0")

    def get_credentials(self, device_id: str) -> dict[str, str]:
        if not _SAFE_DEVICE_ID.match(device_id or ""):
            raise CredentialError(
                f"device_id {device_id!r} is not allowed by the command provider: use letters, "
                "digits, '.', '_', ':' or '-', starting with a letter or digit."
            )
        known_raw = os.getenv("SLC_KNOWN_DEVICE_IDS")
        if known_raw:
            known = {d.strip() for d in known_raw.split(",") if d.strip()}
            if device_id not in known:
                raise CredentialError(f"device_id {device_id!r} is not in SLC_KNOWN_DEVICE_IDS.")

        argv = [arg.replace(_PLACEHOLDER, device_id) for arg in self._argv]
        name = argv[0]
        env = dict(os.environ, SLC_DEVICE_ID=device_id)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CredentialError(f"Credential command not found: {name}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CredentialError(
                f"Credential command {name} timed out after {self._timeout:g}s for {device_id!r}"
            ) from exc

        if proc.returncode != 0:
            detail = (proc.stderr or "").strip()[:_STDERR_LIMIT]
            msg = f"Credential command {name} exited with status {proc.returncode} for {device_id!r}"
            raise CredentialError(f"{msg}: {detail}" if detail else msg)

        try:
            data = json.loads(proc.stdout or "")
        except json.JSONDecodeError as exc:
            raise CredentialError(
                f"Credential command {name} must print a JSON object for {device_id!r}"
            ) from exc
        if not isinstance(data, dict):
            raise CredentialError(f"Credential command {name} must print a JSON object for {device_id!r}")

        missing = [f for f in ("ip", "username", "password") if not data.get(f)]
        if missing:
            raise CredentialError(
                f"Credential command output for {device_id!r} is missing: {', '.join(missing)}"
            )
        return {
            "ip": str(data["ip"]),
            "username": str(data["username"]),
            "password": str(data["password"]),
            "totp_secret": str(data["totp_secret"]) if data.get("totp_secret") else None,
        }
