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
