"""
Unit tests for protocol.py
===========================
Message framing, delta helpers, struct validation, backpressure helpers.
"""

import json
import pytest
from ..protocol import (
    C2S, S2C, InputOp,
    make_message, parse_message, validate_message,
    compute_delta, apply_delta,
    calc_allow_rate, should_drop_input,
    INPUT_QUEUE_WARN, INPUT_QUEUE_DROP,
)


class TestFraming:
    def test_make_message_roundtrip(self):
        raw = make_message(C2S.INPUT, {'type': 'move', 'unit_uid': 1}, seq=5, tick=10)
        msg = parse_message(raw)
        assert msg['t'] == C2S.INPUT
        assert msg['seq'] == 5
        assert msg['tick'] == 10
        assert msg['d'] == {'type': 'move', 'unit_uid': 1}
        assert 'ts' in msg

    def test_make_message_defaults(self):
        raw = make_message(C2S.HEARTBEAT, {})
        msg = parse_message(raw)
        assert msg['t'] == C2S.HEARTBEAT
        assert msg['seq'] == 0
        assert msg['tick'] == 0
        assert msg['d'] == {}

    def test_parse_message_missing_t(self):
        with pytest.raises(ValueError, match='Missing message type'):
            parse_message('{}')
        with pytest.raises(ValueError, match='Missing message type'):
            parse_message('{"x": 1}')

    def test_parse_message_not_dict(self):
        with pytest.raises(ValueError, match='Missing message type'):
            parse_message('"string"')

    def test_parse_message_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            parse_message('not json')

    def test_parse_message_fills_defaults(self):
        msg = parse_message('{"t": 1}')
        assert msg['seq'] == 0
        assert msg['ts'] == 0
        assert msg['tick'] == 0
        assert msg['d'] == {}

    def test_s2c_flow_control_type(self):
        assert int(S2C.FLOW_CONTROL) == 137


class TestValidation:
    def test_input_valid(self):
        assert validate_message(C2S.INPUT, {'type': 'move'}) is None

    def test_input_missing_type(self):
        err = validate_message(C2S.INPUT, {})
        assert err is not None and 'type' in err

    def test_input_wrong_type(self):
        err = validate_message(C2S.INPUT, {'type': 123})
        assert err is not None and 'str' in err

    def test_unknown_type_passes(self):
        assert validate_message(999, {'x': 1}) is None

    def test_join_battle_no_required(self):
        assert validate_message(C2S.JOIN_BATTLE, {}) is None
        assert validate_message(C2S.JOIN_BATTLE, {'extra': 1}) is None

    def test_snapshot_req_no_required(self):
        assert validate_message(C2S.SNAPSHOT_REQ, {}) is None


class TestSeqFlowControl:
    def test_calc_allow_rate_below_warn(self):
        assert calc_allow_rate(0) == 30
        assert calc_allow_rate(50) == 30
        assert calc_allow_rate(INPUT_QUEUE_WARN) == 30

    def test_calc_allow_rate_at_drop(self):
        assert calc_allow_rate(INPUT_QUEUE_DROP) == 2

    def test_calc_allow_rate_mid(self):
        mid = (INPUT_QUEUE_WARN + INPUT_QUEUE_DROP) // 2
        rate = calc_allow_rate(mid)
        assert 2 <= rate <= 30

    def test_calc_allow_rate_beyond_drop(self):
        assert calc_allow_rate(10000) == 2

    def test_calc_allow_rate_custom_range(self):
        rate = calc_allow_rate(5, warn=3, drop=10, max_rate=20, min_rate=1)
        assert 1 <= rate <= 20

    def test_should_drop(self):
        assert should_drop_input(INPUT_QUEUE_DROP) is True
        assert should_drop_input(INPUT_QUEUE_DROP + 100) is True
        assert should_drop_input(0) is False
        assert should_drop_input(INPUT_QUEUE_DROP - 1) is False
        assert should_drop_input(INPUT_QUEUE_WARN) is False


class TestDelta:
    def test_compute_delta_new_keys(self):
        old = {'a': 1}
        new = {'a': 1, 'b': 2}
        assert compute_delta(old, new) == {'b': 2}

    def test_compute_delta_changed_keys(self):
        old = {'a': 1, 'b': 2}
        new = {'a': 1, 'b': 3}
        assert compute_delta(old, new) == {'b': 3}

    def test_compute_delta_deleted_keys(self):
        old = {'a': 1, 'b': 2}
        new = {'a': 1}
        assert compute_delta(old, new) == {'b': None}

    def test_compute_delta_no_changes(self):
        old = {'a': 1}
        new = {'a': 1}
        assert compute_delta(old, new) == {}

    def test_compute_delta_empty_old(self):
        old = {}
        new = {'a': 1}
        assert compute_delta(old, new) == {'a': 1}

    def test_apply_delta_add(self):
        state = {'a': 1}
        apply_delta(state, {'b': 2})
        assert state == {'a': 1, 'b': 2}

    def test_apply_delta_update(self):
        state = {'a': 1}
        apply_delta(state, {'a': 2})
        assert state == {'a': 2}

    def test_apply_delta_delete(self):
        state = {'a': 1, 'b': 2}
        apply_delta(state, {'b': None})
        assert state == {'a': 1}
        assert 'b' not in state

    def test_apply_delta_combined(self):
        state = {'a': 1, 'b': 2, 'c': 3}
        apply_delta(state, {'a': 10, 'b': None, 'd': 4})
        assert state == {'a': 10, 'c': 3, 'd': 4}
        assert 'b' not in state

    def test_delta_commutes(self):
        old = {'x': 1, 'y': 2}
        new = {'x': 5, 'z': 3}
        delta = compute_delta(old, new)
        result = dict(old)
        apply_delta(result, delta)
        assert result == new
