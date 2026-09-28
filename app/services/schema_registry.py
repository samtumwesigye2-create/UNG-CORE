from __future__ import annotations
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class SchemaVersion:
    name: str
    version: str
    content: str
    sha256: str
    deprecated: bool = False


class SchemaRegistry:
    """Stores canonical schemas and simple compatibility metadata."""

    def __init__(self) -> None:
        self._schemas: dict[tuple[str, str], SchemaVersion] = {}

    def register(self, name: str, version: str, content: str) -> SchemaVersion:
        if not name or not version or not content:
            raise ValueError("name, version and content are required")
        key=(name, version)
        if key in self._schemas:
            raise ValueError("schema version already exists")
        item=SchemaVersion(name, version, content, hashlib.sha256(content.encode()).hexdigest())
        self._schemas[key]=item
        return item

    def get(self, name: str, version: str) -> SchemaVersion:
        return self._schemas[(name, version)]

    def deprecate(self, name: str, version: str) -> SchemaVersion:
        from dataclasses import replace
        key=(name, version)
        updated=replace(self._schemas[key], deprecated=True)
        self._schemas[key]=updated
        return updated

    def versions(self, name: str) -> tuple[SchemaVersion, ...]:
        return tuple(sorted(
            (s for (n,_),s in self._schemas.items() if n==name),
            key=lambda s: s.version
        ))

    @staticmethod
    def require_fields_compatible(old_fields: set[str], new_fields: set[str]) -> bool:
        return old_fields.issubset(new_fields)
