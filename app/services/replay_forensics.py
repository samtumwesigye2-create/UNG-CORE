from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class ReplayRecord:
    sequence: int
    timestamp_ns: int
    stream: str
    payload: dict[str, Any]
    config_version: str | None = None
    model_version: str | None = None
    previous_hash: str = ""
    record_hash: str = ""


class ReplayRecorder:
    """Append-only replay log with a simple hash chain for tamper evidence."""

    def __init__(self) -> None:
        self._records: list[ReplayRecord] = []

    @staticmethod
    def _hash(data: dict[str, Any]) -> str:
        raw=json.dumps(data, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()

    def append(
        self,
        *,
        timestamp_ns: int,
        stream: str,
        payload: dict[str, Any],
        config_version: str | None = None,
        model_version: str | None = None,
    ) -> ReplayRecord:
        sequence=len(self._records)+1
        previous_hash=self._records[-1].record_hash if self._records else ""
        base={
            "sequence":sequence,
            "timestamp_ns":int(timestamp_ns),
            "stream":stream,
            "payload":dict(payload),
            "config_version":config_version,
            "model_version":model_version,
            "previous_hash":previous_hash,
        }
        record=ReplayRecord(**base, record_hash=self._hash(base))
        self._records.append(record)
        return record

    def verify(self) -> bool:
        previous=""
        for record in self._records:
            base=asdict(record)
            record_hash=base.pop("record_hash")
            if base["previous_hash"] != previous or self._hash(base) != record_hash:
                return False
            previous=record_hash
        return True

    def between(self, start_ns: int, end_ns: int) -> tuple[ReplayRecord,...]:
        return tuple(r for r in self._records if start_ns <= r.timestamp_ns <= end_ns)
