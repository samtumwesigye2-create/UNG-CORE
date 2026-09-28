from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable


class TaskState(str, Enum):
    PENDING="pending"
    READY="ready"
    RUNNING="running"
    PAUSED="paused"
    COMPLETED="completed"
    CANCELLED="cancelled"
    FAILED="failed"


@dataclass(frozen=True)
class WorkflowTask:
    task_id: str
    kind: str
    dependencies: tuple[str,...] = ()
    required_resources: tuple[str,...] = ()
    priority: int = 0
    state: TaskState = TaskState.PENDING


class MissionWorkflowEngine:
    """Dependency-aware benign workflow engine for mapping, inspection, delivery and surveying."""

    def __init__(self) -> None:
        self._tasks: dict[str,WorkflowTask]={}

    def add(self, task: WorkflowTask) -> WorkflowTask:
        if task.task_id in self._tasks:
            raise ValueError("task already exists")
        if task.task_id in task.dependencies:
            raise ValueError("task cannot depend on itself")
        self._tasks[task.task_id]=task
        return task

    def refresh_readiness(self) -> tuple[WorkflowTask,...]:
        changed=[]
        for task_id, task in list(self._tasks.items()):
            if task.state is not TaskState.PENDING:
                continue
            if all(
                dep in self._tasks and self._tasks[dep].state is TaskState.COMPLETED
                for dep in task.dependencies
            ):
                updated=replace(task,state=TaskState.READY)
                self._tasks[task_id]=updated
                changed.append(updated)
        return tuple(changed)

    def transition(self, task_id: str, target: TaskState) -> WorkflowTask:
        current=self._tasks[task_id]
        allowed={
            TaskState.PENDING:{TaskState.CANCELLED},
            TaskState.READY:{TaskState.RUNNING,TaskState.CANCELLED},
            TaskState.RUNNING:{TaskState.PAUSED,TaskState.COMPLETED,TaskState.FAILED,TaskState.CANCELLED},
            TaskState.PAUSED:{TaskState.RUNNING,TaskState.CANCELLED},
            TaskState.COMPLETED:set(),
            TaskState.CANCELLED:set(),
            TaskState.FAILED:{TaskState.READY,TaskState.CANCELLED},
        }
        if target not in allowed[current.state]:
            raise ValueError(f"invalid transition {current.state}->{target}")
        updated=replace(current,state=target)
        self._tasks[task_id]=updated
        return updated

    def ready(self) -> tuple[WorkflowTask,...]:
        return tuple(sorted(
            (t for t in self._tasks.values() if t.state is TaskState.READY),
            key=lambda t:(-t.priority,t.task_id)
        ))
