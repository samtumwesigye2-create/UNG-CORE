from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class CalibrationRecord:
    component_id: str
    kind: str
    version: int
    payload: dict[str, Any]
    checksum_sha256: str
    created_at_utc: str


class CalibrationRegistry:
    """Versioned immutable configuration/calibration registry."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, int], CalibrationRecord] = {}
        self._active: dict[tuple[str, str], int] = {}

    @staticmethod
    def _checksum(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def register(self, component_id: str, kind: str, payload: dict[str, Any]) -> CalibrationRecord:
        if not component_id or not kind:
            raise ValueError("component_id and kind are required")
        key = (component_id, kind)
        versions = [version for cid, ck, version in self._records if (cid, ck) == key]
        version = max(versions, default=0) + 1
        record = CalibrationRecord(
            component_id=component_id,
            kind=kind,
            version=version,
            payload=dict(payload),
            checksum_sha256=self._checksum(payload),
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        self._records[(component_id, kind, version)] = record
        return record

    def activate(self, component_id: str, kind: str, version: int) -> CalibrationRecord:
        record = self._records.get((component_id, kind, int(version)))
        if record is None:
            raise KeyError("calibration version not found")
        if self._checksum(record.payload) != record.checksum_sha256:
            raise ValueError("calibration checksum mismatch")
        self._active[(component_id, kind)] = record.version
        return record

    def active(self, component_id: str, kind: str) -> CalibrationRecord | None:
        version = self._active.get((component_id, kind))
        if version is None:
            return None
        return self._records[(component_id, kind, version)]

    def history(self, component_id: str, kind: str) -> list[CalibrationRecord]:
        return sorted(
            [
                record
                for (cid, ck, _), record in self._records.items()
                if cid == component_id and ck == kind
            ],
            key=lambda item: item.version,
        )
