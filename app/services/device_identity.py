from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable


class DeviceTrustState(str, Enum):
    PENDING = "pending"
    TRUSTED = "trusted"
    QUARANTINED = "quarantined"
    REVOKED = "revoked"


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    certificate_fingerprint: str
    hardware_id: str
    software_version: str
    owner_system: str
    trust_state: DeviceTrustState = DeviceTrustState.PENDING


class DeviceIdentityRegistry:
    """Tracks device identity, certificate fingerprints and quarantine/revocation state."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceIdentity] = {}

    def enroll(self, identity: DeviceIdentity) -> DeviceIdentity:
        if not identity.device_id or not identity.certificate_fingerprint:
            raise ValueError("device_id and certificate_fingerprint are required")
        if identity.device_id in self._devices:
            raise ValueError("device already enrolled")
        if any(x.certificate_fingerprint == identity.certificate_fingerprint for x in self._devices.values()):
            raise ValueError("certificate fingerprint already in use")
        self._devices[identity.device_id] = identity
        return identity

    def set_trust(self, device_id: str, state: DeviceTrustState) -> DeviceIdentity:
        current = self._devices[device_id]
        updated = replace(current, trust_state=DeviceTrustState(state))
        self._devices[device_id] = updated
        return updated

    def rotate_certificate(self, device_id: str, new_fingerprint: str) -> DeviceIdentity:
        if not new_fingerprint:
            raise ValueError("new fingerprint is required")
        if any(
            d.device_id != device_id and d.certificate_fingerprint == new_fingerprint
            for d in self._devices.values()
        ):
            raise ValueError("certificate fingerprint already in use")
        current = self._devices[device_id]
        updated = replace(current, certificate_fingerprint=new_fingerprint)
        self._devices[device_id] = updated
        return updated

    def get(self, device_id: str) -> DeviceIdentity:
        return self._devices[device_id]

    def trusted_devices(self) -> Iterable[DeviceIdentity]:
        return tuple(d for d in self._devices.values() if d.trust_state is DeviceTrustState.TRUSTED)
