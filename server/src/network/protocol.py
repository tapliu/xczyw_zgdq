"""
Network Protocol Layer
======================
Layer 2: message framing, type definitions, seq sliding window,
         struct validation, backpressure protocol.

Frame:  { t: type, seq: seq#, ts: timestamp_ms, tick: frame#, d: payload }
"""

import json
import time
from enum import IntEnum
from typing import Any, Optional

# ── Seq Sliding Window ─────────────────────────────────────────────────
# Server tracks last N processed seqs per peer to reject duplicates.
SEQ_WINDOW_SIZE = 256
# Flow control: max unacknowledged inputs before we push back.
MAX_UNACKED = SEQ_WINDOW_SIZE // 2  # 128


# ── Backpressure Watermarks ────────────────────────────────────────────
# Input queue (server-side per-session).
INPUT_QUEUE_WARN = 100     # ⚠ push FLOW_CONTROL with backpressure=false
INPUT_QUEUE_DROP = 300     # ✂ discard new inputs + push backpressure=true
# Peer send queue.
SEND_QUEUE_WARN = 50
SEND_QUEUE_DROP = 150


class C2S(IntEnum):
    HEARTBEAT = 1
    JOIN_BATTLE = 2
    LEAVE = 3
    INPUT = 4           # {type, unit_uid, ...}
    PING = 5
    SNAPSHOT_REQ = 6   # request full state snapshot (reconnection)


class S2C(IntEnum):
    HEARTBEAT = 129
    STATE = 130         # d: {full: bool, snapshot/delta, tick}
    ACK = 131           # d: {seq, tick?}
    ERROR = 132         # d: {message, seq?}
    PHASE = 133         # d: {phase, round, role}
    EVENT = 134         # d: battle event
    PONG = 135
    SNAPSHOT_RES = 136  # d: {snapshot, tick}  (reconnection response)
    FLOW_CONTROL = 137  # d: {queue_backlog, allow_rate, backpressure}


# ── Input Operation Types ──────────────────────────────────────────────

class InputOp:
    MOVE = 'move'
    ATTACK = 'attack'
    ABILITY = 'ability'
    HOLD = 'hold'


# ── Event Types ────────────────────────────────────────────────────────

class EventType:
    MOVED = 'moved'
    ATTACKED = 'attacked'
    DIED = 'died'
    PHASE_CHANGE = 'phase_change'
    COMBAT_RESULT = 'combat'


# ── Message Struct Validation (Layer 2.5) ──────────────────────────────

_MESSAGE_SCHEMAS = {
    C2S.INPUT: {
        'required': ['type'],
        'type_map': {'type': str},
    },
    C2S.JOIN_BATTLE: {'required': [], 'type_map': {}},
    C2S.SNAPSHOT_REQ: {'required': [], 'type_map': {}},
}


def validate_message(t: int, data: dict) -> Optional[str]:
    """Return error string if message is structurally invalid, else None."""
    schema = _MESSAGE_SCHEMAS.get(t)
    if schema is None:
        return None  # unknown type passes basic validation
    for key in schema['required']:
        if key not in data:
            return f'missing required field: {key}'
    for key, expected_type in schema.get('type_map', {}).items():
        if key in data and not isinstance(data[key], expected_type):
            return f'field {key} should be {expected_type.__name__}'
    return None


# ── Framing ────────────────────────────────────────────────────────────

# ── Backpressure Helpers ──────────────────────────────────────────────


def calc_allow_rate(queue_depth: int, warn: int = INPUT_QUEUE_WARN,
                    drop: int = INPUT_QUEUE_DROP,
                    max_rate: int = 30, min_rate: int = 2) -> int:
    """
    Linear mapping: queue_depth → allowed inputs/sec.

    - 0 .. warn        → max_rate
    - warn .. drop     → linearly from max_rate down to min_rate
    - >= drop          → min_rate
    """
    if queue_depth <= warn:
        return max_rate
    if queue_depth >= drop:
        return min_rate
    ratio = (queue_depth - warn) / (drop - warn)
    return max(int(max_rate - ratio * (max_rate - min_rate)), min_rate)


def should_drop_input(queue_depth: int, drop: int = INPUT_QUEUE_DROP) -> bool:
    """True when the input queue exceeds the drop watermark."""
    return queue_depth >= drop


# ── Framing ────────────────────────────────────────────────────────────

def make_message(msg_type: int, data: dict, seq: int = 0, tick: int = 0) -> str:
    return json.dumps({
        't': int(msg_type),
        'seq': seq,
        'ts': int(time.time() * 1000),
        'tick': tick,
        'd': data,
    }, ensure_ascii=False)


def parse_message(raw: str) -> dict:
    msg = json.loads(raw)
    if not isinstance(msg, dict) or 't' not in msg:
        raise ValueError('Missing message type')
    msg.setdefault('seq', 0)
    msg.setdefault('ts', 0)
    msg.setdefault('tick', 0)
    msg.setdefault('d', {})
    return msg


# ── State Delta Helpers ────────────────────────────────────────────────

def compute_delta(old: dict, new: dict) -> dict:
    """Return only the changed top-level keys between two state dicts."""
    delta = {}
    for k in new:
        if k not in old or old[k] != new[k]:
            delta[k] = new[k]
    # Mark deleted keys (if any)
    for k in old:
        if k not in new:
            delta[k] = None
    return delta


def apply_delta(state: dict, delta: dict) -> dict:
    """Apply a delta patch to a state dict in-place."""
    for k, v in delta.items():
        if v is None:
            state.pop(k, None)
        else:
            state[k] = v
    return state
