from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

T=TypeVar("T")


@dataclass(frozen=True)
class VerificationResult:
    name: str
    passed: bool
    detail: str = ""


def check_invariant(name: str, states: Iterable[T], predicate: Callable[[T], bool]) -> VerificationResult:
    for index, state in enumerate(states):
        if not predicate(state):
            return VerificationResult(name, False, f"invariant failed at state {index}: {state!r}")
    return VerificationResult(name, True)


def verify_transition_graph(
    name: str,
    transitions: dict[str, set[str]],
    *,
    terminal_states: set[str] | None = None,
) -> VerificationResult:
    terminal_states=terminal_states or set()
    for state, destinations in transitions.items():
        if state in terminal_states and destinations:
            return VerificationResult(name, False, f"terminal state {state} has outgoing transitions")
        for destination in destinations:
            if destination not in transitions and destination not in terminal_states:
                return VerificationResult(name, False, f"unknown destination {destination}")
    return VerificationResult(name, True)


def boundary_vectors(minimum: int, maximum: int) -> tuple[int,...]:
    if minimum > maximum:
        raise ValueError("minimum cannot exceed maximum")
    values={minimum, maximum}
    if minimum < maximum:
        values.update({minimum+1, maximum-1})
    if minimum <= 0 <= maximum:
        values.add(0)
    return tuple(sorted(values))
