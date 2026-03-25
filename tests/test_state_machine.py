from __future__ import annotations

import pytest

from app.state.state_machine import EngineState, StateMachine


class TestStateMachine:
    def test_initial_state_is_idle(self):
        sm = StateMachine()
        assert sm.state == EngineState.IDLE

    def test_custom_initial_state(self):
        sm = StateMachine(initial_state=EngineState.SCANNING)
        assert sm.state == EngineState.SCANNING

    def test_valid_transition_idle_to_scanning(self):
        sm = StateMachine()
        result = sm.transition(EngineState.SCANNING)
        assert result == EngineState.SCANNING
        assert sm.state == EngineState.SCANNING

    def test_invalid_transition_raises(self):
        sm = StateMachine()
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(EngineState.EXECUTING)

    def test_halted_is_terminal(self):
        sm = StateMachine(initial_state=EngineState.HALTED)
        assert sm.allowed_transitions() == ()
        with pytest.raises(ValueError):
            sm.transition(EngineState.SCANNING)

    def test_every_state_can_halt(self):
        for state in EngineState:
            if state == EngineState.HALTED:
                continue
            sm = StateMachine(initial_state=state)
            assert sm.can_transition(EngineState.HALTED)

    def test_allowed_transitions_not_empty_for_non_halted(self):
        for state in EngineState:
            sm = StateMachine(initial_state=state)
            transitions = sm.allowed_transitions()
            if state == EngineState.HALTED:
                assert len(transitions) == 0
            else:
                assert len(transitions) > 0

    @pytest.mark.parametrize("from_state,to_state", [
        (EngineState.IDLE, EngineState.SCANNING),
        (EngineState.SCANNING, EngineState.SETUP_FOUND),
        (EngineState.SETUP_FOUND, EngineState.VALIDATING),
        (EngineState.VALIDATING, EngineState.EXECUTING),
        (EngineState.EXECUTING, EngineState.POSITION_OPEN),
        (EngineState.POSITION_OPEN, EngineState.SCANNING),
        (EngineState.COOLDOWN, EngineState.SCANNING),
    ])
    def test_valid_transitions(self, from_state, to_state):
        sm = StateMachine(initial_state=from_state)
        sm.transition(to_state)
        assert sm.state == to_state
