from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any


class BackupState(str, Enum):
    CREATED="created"
    VERIFIED="verified"
    RESTORED="restored"
    FAILED="failed"


@dataclass(frozen=True)
class BackupSnapshot:
    snapshot_id: str
    created_epoch_s: int
    payload_sha256: str
    rpo_seconds: int
    rto_seconds: int
    state: BackupState = BackupState.CREATED


class DisasterRecoveryManager:
    """Tracks backup integrity and restore-test evidence."""

    def __init__(self) -> None:
        self._snapshots: dict[str,BackupSnapshot]={}

    @staticmethod
    def canonical_bytes(payload: dict[str,Any]) -> bytes:
        return json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()

    def create(self, snapshot_id: str, created_epoch_s: int, payload: dict[str,Any], *, rpo_seconds: int, rto_seconds: int) -> BackupSnapshot:
        if snapshot_id in self._snapshots:
            raise ValueError("snapshot already exists")
        digest=hashlib.sha256(self.canonical_bytes(payload)).hexdigest()
        snap=BackupSnapshot(snapshot_id,int(created_epoch_s),digest,int(rpo_seconds),int(rto_seconds))
        self._snapshots[snapshot_id]=snap
        return snap

    def verify(self, snapshot_id: str, payload: dict[str,Any]) -> BackupSnapshot:
        from dataclasses import replace
        current=self._snapshots[snapshot_id]
        ok=current.payload_sha256==hashlib.sha256(self.canonical_bytes(payload)).hexdigest()
        updated=replace(current,state=BackupState.VERIFIED if ok else BackupState.FAILED)
        self._snapshots[snapshot_id]=updated
        return updated

    def mark_restore_test(self, snapshot_id: str, *, success: bool) -> BackupSnapshot:
        from dataclasses import replace
        current=self._snapshots[snapshot_id]
        if current.state is not BackupState.VERIFIED:
            raise RuntimeError("backup must be verified before restore testing")
        updated=replace(current,state=BackupState.RESTORED if success else BackupState.FAILED)
        self._snapshots[snapshot_id]=updated
        return updated
