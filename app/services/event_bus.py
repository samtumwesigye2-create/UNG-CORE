from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    topic: str
    payload: Any
    sequence: int


class EventBus:
    """In-process async pub/sub backbone with bounded subscriber queues."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = {}
        self._sequence=0
        self.dropped_events=0

    def subscribe(self, topic: str, *, max_queue: int = 256) -> asyncio.Queue[Event]:
        if max_queue <= 0:
            raise ValueError("max_queue must be positive")
        queue:asyncio.Queue[Event]=asyncio.Queue(maxsize=max_queue)
        self._subscribers.setdefault(topic, set()).add(queue)
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue[Event]) -> None:
        subscribers=self._subscribers.get(topic)
        if subscribers:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(topic, None)

    def publish_nowait(self, topic: str, payload: Any) -> Event:
        self._sequence += 1
        event=Event(topic, payload, self._sequence)
        for queue in tuple(self._subscribers.get(topic, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.dropped_events += 1
        return event
