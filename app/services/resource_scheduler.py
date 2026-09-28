from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum


class Priority(IntEnum):
    BACKGROUND=10
    NORMAL=20
    HIGH=30
    REALTIME=40


@dataclass(frozen=True)
class ResourceBudget:
    cpu: float = 0.0
    gpu: float = 0.0
    npu: float = 0.0
    fpga: float = 0.0
    memory_mb: int = 0
    bandwidth_mbps: float = 0.0


@dataclass(order=True, frozen=True)
class WorkItem:
    sort_key: tuple = field(init=False, repr=False)
    priority: Priority
    deadline_ns: int
    work_id: str
    budget: ResourceBudget

    def __post_init__(self) -> None:
        object.__setattr__(self, "sort_key", (-int(self.priority), self.deadline_ns, self.work_id))


class ResourceScheduler:
    """Admission-control queue for CPU/GPU/NPU/FPGA workloads."""

    def __init__(self, capacity: ResourceBudget) -> None:
        self.capacity=capacity
        self._queue:list[WorkItem]=[]

    @staticmethod
    def _fits(need: ResourceBudget, cap: ResourceBudget) -> bool:
        return (
            need.cpu <= cap.cpu and need.gpu <= cap.gpu and need.npu <= cap.npu and
            need.fpga <= cap.fpga and need.memory_mb <= cap.memory_mb and
            need.bandwidth_mbps <= cap.bandwidth_mbps
        )

    def submit(self, item: WorkItem) -> None:
        if not self._fits(item.budget, self.capacity):
            raise ValueError("work item exceeds scheduler capacity")
        self._queue.append(item)
        self._queue.sort(key=lambda x: x.sort_key)

    def next(self) -> WorkItem | None:
        return self._queue.pop(0) if self._queue else None

    def pending(self) -> tuple[WorkItem, ...]:
        return tuple(self._queue)
