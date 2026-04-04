from __future__ import annotations

import pytest

from app.state.state_machine import EngineState, StateMachine


class TestStateMachine:
    def test_initial_state_is_idle(self) -> None:
        sm = StateMachine()
        assert sm.state == EngineState.IDLE

    def test_custom_initial_state(self) -> None:
        sm = StateMachine(initial_state=EngineState.SCANNING)
        assert sm.state == EngineState.SCANNING

    def test_valid_transition(self) -> None:
        sm = StateMachine()
        result = sm.transition(EngineState.SCANNING)
        assert result == EngineState.SCANNING
        assert sm.state == EngineState.SCANNING

    def test_invalid_transition_raises(self) -> None:
        sm = StateMachine()
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(EngineState.EXECUTING)

    def test_can_transition(self) -> None:
        sm = StateMachine()
        assert sm.can_transition(EngineState.SCANNING) is True
        assert sm.can_transition(EngineState.EXECUTING) is False

    def test_halted_is_terminal(self) -> None:
        sm = StateMachine()
        sm.transition(EngineState.HALTED)
        assert sm.allowed_transitions() == ()

    def test_full_happy_path(self) -> None:
        sm = StateMachine()
        path = [
            EngineState.SCANNING,
            EngineState.SETUP_FOUND,
            EngineState.VALIDATING,
            EngineState.EXECUTING,
            EngineState.POSITION_OPEN,
            EngineState.SCANNING,
        ]
        for state in path:
            sm.transition(state)
        assert sm.state == EngineState.SCANNING

    def test_cooldown_returns_to_scanning(self) -> None:
        sm = StateMachine(initial_state=EngineState.VALIDATING)
        sm.transition(EngineState.COOLDOWN)
        sm.transition(EngineState.SCANNING)
        assert sm.state == EngineState.SCANNING

    def test_any_state_can_halt(self) -> None:
        for start in EngineState:
            if start == EngineState.HALTED:
                continue
            sm = StateMachine(initial_state=start)
            sm.transition(EngineState.HALTED)
            assert sm.state == EngineState.HALTED
