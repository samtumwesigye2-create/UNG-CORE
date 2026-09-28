from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib


class UpdateState(str, Enum):
    IDLE = "idle"
    STAGED = "staged"
    PENDING_REBOOT = "pending_reboot"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    artifact_sha256: str
    compatible_platforms: tuple[str, ...]
    minimum_current_version: str | None = None


class OtaRollbackManager:
    """A/B-style update state machine.

    Signature verification is intentionally delegated to the platform trust
    service/HSM. This class only accepts an explicit verified result.
    """

    def __init__(self, platform_id: str, current_version: str) -> None:
        self.platform_id = platform_id
        self.current_version = current_version
        self.state = UpdateState.IDLE
        self.staged_manifest: UpdateManifest | None = None
        self.previous_version: str | None = None

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def stage(self, manifest: UpdateManifest, artifact: bytes, *, signature_verified: bool) -> UpdateState:
        if not signature_verified:
            self.state = UpdateState.REJECTED
            return self.state
        if self.platform_id not in manifest.compatible_platforms:
            self.state = UpdateState.REJECTED
            return self.state
        if self.sha256(artifact) != manifest.artifact_sha256.lower():
            self.state = UpdateState.REJECTED
            return self.state
        self.staged_manifest = manifest
        self.state = UpdateState.STAGED
        return self.state

    def mark_reboot_pending(self) -> UpdateState:
        if self.state is not UpdateState.STAGED or self.staged_manifest is None:
            raise RuntimeError("no verified update staged")
        self.previous_version = self.current_version
        self.state = UpdateState.PENDING_REBOOT
        return self.state

    def begin_boot_verification(self) -> UpdateState:
        if self.state is not UpdateState.PENDING_REBOOT:
            raise RuntimeError("update is not pending reboot")
        self.state = UpdateState.VERIFYING
        return self.state

    def complete_boot_verification(self, *, healthy: bool) -> UpdateState:
        if self.state is not UpdateState.VERIFYING or self.staged_manifest is None:
            raise RuntimeError("boot verification not active")
        if healthy:
            self.current_version = self.staged_manifest.version
            self.state = UpdateState.COMMITTED
        else:
            if self.previous_version is not None:
                self.current_version = self.previous_version
            self.state = UpdateState.ROLLED_BACK
        return self.state
