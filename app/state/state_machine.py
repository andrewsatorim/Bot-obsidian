from __future__ import annotations

from enum import Enum
from typing import Iterable


class EngineState(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    SETUP_FOUND = "SETUP_FOUND"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    POSITION_OPEN = "POSITION_OPEN"
    COOLDOWN = "COOLDOWN"
    HALTED = "HALTED"


class StateMachine:
    """Simple deterministic state machine for the trading engine lifecycle."""

    _ALLOWED_TRANSITIONS: dict[EngineState, set[EngineState]] = {
        EngineState.IDLE: {EngineState.SCANNING, EngineState.HALTED},
        EngineState.SCANNING: {EngineState.SETUP_FOUND, EngineState.COOLDOWN, EngineState.HALTED},
        EngineState.SETUP_FOUND: {EngineState.VALIDATING, EngineState.SCANNING, EngineState.HALTED},
        EngineState.VALIDATING: {
            EngineState.EXECUTING,
            EngineState.SCANNING,
            EngineState.COOLDOWN,
            EngineState.HALTED,
        },
        EngineState.EXECUTING: {EngineState.POSITION_OPEN, EngineState.SCANNING, EngineState.HALTED},
        EngineState.POSITION_OPEN: {EngineState.SCANNING, EngineState.COOLDOWN, EngineState.HALTED},
        EngineState.COOLDOWN: {EngineState.SCANNING, EngineState.HALTED},
        EngineState.HALTED: set(),
    }

    def __init__(self, initial_state: EngineState = EngineState.IDLE) -> None:
        self._state = initial_state

    @property
    def state(self) -> EngineState:
        return self._state

    def can_transition(self, next_state: EngineState) -> bool:
        return next_state in self._ALLOWED_TRANSITIONS[self._state]

    def transition(self, next_state: EngineState) -> EngineState:
        if not self.can_transition(next_state):
            raise ValueError(f"Invalid transition: {self._state} -> {next_state}")
        self._state = next_state
        return self._state

    def allowed_transitions(self) -> Iterable[EngineState]:
        return tuple(self._ALLOWED_TRANSITIONS[self._state])
