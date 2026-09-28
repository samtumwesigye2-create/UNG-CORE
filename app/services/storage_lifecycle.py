from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib


class StorageTier(str, Enum):
    HOT="hot"
    WARM="warm"
    COLD="cold"


@dataclass
class StoredObject:
    object_id: str
    size_bytes: int
    tier: StorageTier
    checksum_sha256: str
    retained_until_epoch_s: int
    synced: bool = False
    deleted: bool = False


class StorageLifecycleManager:
    def __init__(self) -> None:
        self._objects: dict[str, StoredObject]={}

    def register(self, object_id: str, data: bytes, tier: StorageTier, retained_until_epoch_s: int) -> StoredObject:
        if object_id in self._objects:
            raise ValueError("object already registered")
        item=StoredObject(
            object_id=object_id,
            size_bytes=len(data),
            tier=StorageTier(tier),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            retained_until_epoch_s=int(retained_until_epoch_s),
        )
        self._objects[object_id]=item
        return item

    def move(self, object_id: str, tier: StorageTier) -> StoredObject:
        item=self._objects[object_id]
        item.tier=StorageTier(tier)
        return item

    def mark_synced(self, object_id: str) -> None:
        self._objects[object_id].synced=True

    def secure_delete(self, object_id: str, now_epoch_s: int) -> None:
        item=self._objects[object_id]
        if now_epoch_s < item.retained_until_epoch_s:
            raise PermissionError("retention period has not expired")
        item.deleted=True

    def verify(self, object_id: str, data: bytes) -> bool:
        return self._objects[object_id].checksum_sha256 == hashlib.sha256(data).hexdigest()
