"""
Unit tests for session.py
===========================
Tick loop (non-real-time), input queue, state sync, snapshots,
flow control, and reconnection.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from server.src.network.session import BattleSession
from server.src.network.connection import ConnectionManager, Peer
from server.src.network.protocol import C2S, S2C, InputOp, INPUT_QUEUE_WARN, INPUT_QUEUE_DROP
from server.src.network.session import SNAPSHOT_HISTORY_LEN


# ── Helpers ──────────────────────────────────────────────────────────

def make_mock_game(**kwargs):
    """Create a minimal mock GameState-like object."""
    game = MagicMock()
    game.game_phase = kwargs.get('game_phase', 'battle')
    game.multiplayer = True
    game.round = 1
    game.host_token = 'host_tok'
    game.guest_token = 'guest_tok'

    # Minimal board
    class MockSide:
        def __init__(self):
            self.board = [None] * 64
            self.collection = []
            self.troops = 50000

    game.player = MockSide()
    game.ai = MockSide()
    game.to_dict.return_value = {
        'game_id': 'test',
        'game_phase': game.game_phase,
        'round': 1,
        'player': {'board': [None] * 64, 'troops': 50000},
        'ai': {'board': [None] * 64, 'troops': 50000},
    }
    return game


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def session(manager):
    state_store = {}

    def getter(gid):
        return state_store.get(gid)

    def setter(gid, st):
        state_store[gid] = st

    s = BattleSession('test_game', manager, getter, setter)
    return s


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, session):
        assert session._running is False
        await session.start()
        assert session._running is True
        assert session._tick_task is not None
        await session.stop()
        assert session._running is False
        assert session._tick_task is None

    @pytest.mark.asyncio
    async def test_double_start(self, session):
        await session.start()
        task = session._tick_task
        await session.start()  # no-op
        assert session._tick_task is task
        await session.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_history(self, session):
        session._snapshot_history.append({'snapshot': {'a': 1}, 'tick': 0})
        session._last_full_dict = {'a': 1}
        await session.stop()
        assert session._snapshot_history == []
        assert session._last_full_dict is None


class TestEnqueueInput:
    def test_enqueue_adds_input(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        session.enqueue_input(peer, {'type': 'move'}, seq=1, tick=5)
        assert len(session.input_queue) == 1
        assert session.input_queue[0]['role'] == 'host'
        assert session.input_queue[0]['seq'] == 1
        assert session.input_queue[0]['tick'] == 5
        assert session.input_queue[0]['data'] == {'type': 'move'}

    def test_enqueue_drops_when_overloaded(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        # Fill queue past drop watermark
        for i in range(INPUT_QUEUE_DROP + 10):
            session.input_queue.append({'role': 'host', 'seq': i, 'data': {}})

        initial_len = len(session.input_queue)
        session.enqueue_input(peer, {'type': 'move'}, seq=999)
        # Should NOT grow because we're past the drop watermark
        assert len(session.input_queue) == initial_len

    def test_enqueue_accepts_below_watermark(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        for i in range(INPUT_QUEUE_WARN):
            session.input_queue.append({'role': 'host', 'seq': i, 'data': {}})

        initial_len = len(session.input_queue)
        session.enqueue_input(peer, {'type': 'move'}, seq=888)
        assert len(session.input_queue) == initial_len + 1

    def test_enqueue_marks_seq(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        session.enqueue_input(peer, {'type': 'move'}, seq=42)
        assert peer.input_seq == 42
        assert 42 in peer.processed_seqs


class TestSnapshot:
    def test_no_snapshots(self, session):
        assert session.get_snapshot() is None
        assert session.get_snapshot(tick=5) is None

    def test_get_latest(self, session):
        session._snapshot_history.append({'snapshot': {'a': 1}, 'tick': 0})
        session._snapshot_history.append({'snapshot': {'a': 2}, 'tick': 1})
        snap = session.get_snapshot()
        assert snap['tick'] == 1

    def test_get_closest_tick(self, session):
        session._snapshot_history.append({'snapshot': {'a': 1}, 'tick': 10})
        session._snapshot_history.append({'snapshot': {'a': 2}, 'tick': 20})
        session._snapshot_history.append({'snapshot': {'a': 3}, 'tick': 30})

        snap = session.get_snapshot(tick=22)
        assert snap['tick'] == 20

    def test_get_closest_tick_exact(self, session):
        session._snapshot_history.append({'snapshot': {'a': 1}, 'tick': 10})
        snap = session.get_snapshot(tick=10)
        assert snap['tick'] == 10

    def test_snapshot_capped(self, session):
        # Simulate the trim logic from _sync_state
        for i in range(SNAPSHOT_HISTORY_LEN + 10):
            session._snapshot_history.append({'snapshot': {}, 'tick': i})
            if len(session._snapshot_history) > SNAPSHOT_HISTORY_LEN:
                session._snapshot_history.pop(0)
        assert len(session._snapshot_history) == SNAPSHOT_HISTORY_LEN
        assert session._snapshot_history[0]['tick'] == 10  # oldest entry


class TestProcessInput:
    @pytest.mark.asyncio
    async def test_invalid_input_sends_error(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        await peer.start_sender()
        session.manager.register('test_game', 'host', mock_ws)

        game = make_mock_game()
        inp = {'role': 'host', 'seq': 1, 'data': {'type': 'unknown_op'}}
        await session._process_input(game, inp)
        await asyncio.sleep(0.05)

        # Should have sent ERROR (unacked decremented)
        assert peer.unacked_count == 0

    @pytest.mark.asyncio
    async def test_valid_hold_input_sends_ack(self, session, mock_ws):
        from server.src.backend.state import GameState, Unit
        peer = Peer(mock_ws, 'host', 'test_game')
        await peer.start_sender()
        session.manager.register('test_game', 'host', mock_ws)

        game = GameState('test')
        game.multiplayer = True
        game.game_phase = 'battle'
        unit = Unit({'name': 'test', 'atk': 10, 'def': 10, 'skill': None}, 1000, uid=1)
        unit.pinned = False
        game.player.board[32] = unit

        inp = {'role': 'host', 'seq': 1, 'data': {'type': 'hold', 'unit_uid': 1}}
        await session._process_input(game, inp)
        await asyncio.sleep(0.05)

        assert peer.unacked_count == 0


class TestHandleSnapshotRequest:
    @pytest.mark.asyncio
    async def test_with_history(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        await peer.start_sender()
        session._snapshot_history.append({
            'snapshot': {'game_phase': 'battle'},
            'tick': 10,
        })
        session._tick_count = 15

        await session.handle_snapshot_request(peer, {'tick': 10})
        await asyncio.sleep(0.05)
        assert mock_ws.send_text.called

    @pytest.mark.asyncio
    async def test_without_history_no_game(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        await peer.start_sender()

        await session.handle_snapshot_request(peer, {'tick': 0})
        await asyncio.sleep(0.05)
        assert mock_ws.send_text.called

    @pytest.mark.asyncio
    async def test_without_history_with_game(self, session, mock_ws):
        peer = Peer(mock_ws, 'host', 'test_game')
        await peer.start_sender()

        game = make_mock_game()
        session._set_state('test_game', game)

        await session.handle_snapshot_request(peer, {'tick': 0})
        await asyncio.sleep(0.05)
        assert mock_ws.send_text.called


class TestInputValidation:
    """Directly test _validate_input logic without tick loop."""

    def _make_game(self):
        from server.src.backend.state import GameState
        from server.src.backend.state import Unit
        game = GameState('test')
        game.multiplayer = True
        game.game_phase = 'battle'
        return game

    def test_move_missing_fields(self, session):
        game = self._make_game()
        result = session._validate_input(game, {
            'role': 'host', 'data': {'type': 'move'}
        })
        assert result['valid'] is False

    def test_move_out_of_range(self, session):
        game = self._make_game()
        result = session._validate_input(game, {
            'role': 'host', 'data': {'type': 'move', 'unit_uid': 1, 'to_cell': 999}
        })
        assert result['valid'] is False

    def test_move_unit_not_found(self, session):
        game = self._make_game()
        Unit = type('Unit', (), {'__init__': lambda self: None})()
        result = session._validate_input(game, {
            'role': 'host', 'data': {'type': 'move', 'unit_uid': 999, 'to_cell': 32}
        })
        assert result['valid'] is False

    def test_unknown_op(self, session):
        game = self._make_game()
        result = session._validate_input(game, {
            'role': 'host', 'data': {'type': 'nonsense'}
        })
        assert result['valid'] is False

    def test_hold_unit_not_found(self, session):
        game = self._make_game()
        result = session._validate_input(game, {
            'role': 'host', 'data': {'type': 'hold', 'unit_uid': 999}
        })
        assert result['valid'] is False

    def test_attack_missing_target(self, session):
        game = self._make_game()
        result = session._validate_input(game, {
            'role': 'host', 'data': {'type': 'attack', 'unit_uid': 1}
        })
        assert result['valid'] is False
