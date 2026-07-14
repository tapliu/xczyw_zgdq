"""
Unit tests for connection.py
=============================
Peer send queue, seq dedup, rate limiter, view filtering, backpressure.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from server.src.network.connection import Peer, ConnectionManager, filter_state_for_role
from server.src.network.protocol import C2S, S2C, SEQ_WINDOW_SIZE, MAX_UNACKED


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.fixture
def peer(mock_ws):
    p = Peer(mock_ws, 'host', 'test_game')
    return p


class TestPeer:
    def test_init(self, peer):
        assert peer.role == 'host'
        assert peer.game_id == 'test_game'
        assert peer.alive is True
        assert peer.input_seq == 0
        assert peer.unacked_count == 0
        assert peer.last_backpressure is False
        assert peer.current_allow_rate == 30

    # ── Seq dedup ───────────────────────────────────────────────────

    def test_is_seq_duplicate_fresh(self, peer):
        assert peer.is_seq_duplicate(1) is False

    def test_mark_and_detect_duplicate(self, peer):
        peer.mark_seq_processed(1)
        assert peer.is_seq_duplicate(1) is True

    def test_seq_below_window(self, peer):
        peer.mark_seq_processed(SEQ_WINDOW_SIZE + 10)
        assert peer.is_seq_duplicate(5) is True  # below window_start

    def test_window_slides(self, peer):
        for seq in range(SEQ_WINDOW_SIZE + 5):
            peer.mark_seq_processed(seq)
        # seq=0 should have been pruned
        assert peer.seq_window_start > 0
        assert 0 not in peer.processed_seqs

    def test_seq_ordering(self, peer):
        for seq in [10, 5, 7, 12]:
            peer.mark_seq_processed(seq)
        assert peer.is_seq_duplicate(5) is True
        assert peer.is_seq_duplicate(6) is False

    # ── Unacked limit ───────────────────────────────────────────────

    def test_unacked_below_limit(self, peer):
        peer.unacked_count = MAX_UNACKED - 1
        assert peer.check_unacked_limit() is False

    def test_unacked_at_limit(self, peer):
        peer.unacked_count = MAX_UNACKED
        assert peer.check_unacked_limit() is True

    def test_unacked_above_limit(self, peer):
        peer.unacked_count = MAX_UNACKED + 10
        assert peer.check_unacked_limit() is True

    # ── Rate limiter ────────────────────────────────────────────────

    def test_rate_limit_allows_first_n(self, peer):
        for _ in range(30):
            assert peer.rate_limit_input() is True

    def test_rate_limit_exceeds(self, peer):
        for _ in range(30):
            peer.rate_limit_input()
        assert peer.rate_limit_input() is False

    def test_rate_limit_refills(self, peer):
        for _ in range(30):
            peer.rate_limit_input()
        peer._rate_last_refill = 0  # force refill
        assert peer.rate_limit_input() is True

    # ── Backpressure state ──────────────────────────────────────────

    def test_backpressure_no_backlog(self, peer):
        peer.update_backpressure_state(0)
        assert peer.current_allow_rate == 30
        assert peer.last_backpressure is False

    def test_backpressure_high_backlog(self, peer):
        peer.update_backpressure_state(300)
        assert peer.current_allow_rate == 2
        assert peer.last_backpressure is True

    def test_backpressure_mid_backlog(self, peer):
        peer.update_backpressure_state(100)
        assert 2 <= peer.current_allow_rate <= 30

    # ── Send queue ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_send_enqueue(self, peer, mock_ws):
        await peer.start_sender()
        await peer.send(S2C.HEARTBEAT, {})
        await asyncio.sleep(0.05)
        assert mock_ws.send_text.called
        await peer.close()

    @pytest.mark.asyncio
    async def test_send_queue_depth(self, peer):
        await peer.start_sender()
        assert peer.get_send_queue_depth() == 0
        await peer.send(S2C.HEARTBEAT, {})
        await peer.send(S2C.HEARTBEAT, {})
        assert peer.get_send_queue_depth() >= 2
        await peer.close()

    @pytest.mark.asyncio
    async def test_send_dead_peer(self, peer, mock_ws):
        await peer.start_sender()
        peer.alive = False
        await peer.send(S2C.HEARTBEAT, {})
        await asyncio.sleep(0.05)
        assert not mock_ws.send_text.called


class TestConnectionManager:
    @pytest.fixture
    def mgr(self):
        return ConnectionManager()

    @pytest.fixture
    def mock_ws(self):
        return MagicMock(send_text=AsyncMock())

    def test_register(self, mgr, mock_ws):
        peer = mgr.register('g1', 'host', mock_ws)
        assert peer.role == 'host'
        assert peer.game_id == 'g1'
        assert mgr.get_peer('g1', 'host') is peer

    def test_register_get_peers(self, mgr, mock_ws):
        mgr.register('g1', 'host', mock_ws)
        mgr.register('g1', 'guest', mock_ws)
        peers = mgr.get_peers('g1')
        assert len(peers) == 2
        assert 'host' in peers
        assert 'guest' in peers

    @pytest.mark.asyncio
    async def test_unregister_removes_peer(self, mgr, mock_ws):
        mgr.register('g1', 'host', mock_ws)
        mgr.unregister('g1', 'host')
        await asyncio.sleep(0.01)
        assert mgr.get_peer('g1', 'host') is None

    @pytest.mark.asyncio
    async def test_unregister_removes_game_when_empty(self, mgr, mock_ws):
        mgr.register('g1', 'host', mock_ws)
        mgr.unregister('g1', 'host')
        await asyncio.sleep(0.01)
        assert 'g1' not in mgr._games

    def test_get_peer_nonexistent(self, mgr):
        assert mgr.get_peer('no', 'host') is None
        assert mgr.get_peers('no') == {}

    def test_broadcast_host_only(self, mgr, mock_ws):
        host_ws = MagicMock(send_text=AsyncMock())
        guest_ws = MagicMock(send_text=AsyncMock())
        mgr.register('g1', 'host', host_ws)
        mgr.register('g1', 'guest', guest_ws)
        asyncio.run(mgr.broadcast('g1', S2C.HEARTBEAT, {}, exclude_role='host'))
        assert not host_ws.send_text.called


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_heartbeat(self):
        ws = MagicMock(send_text=AsyncMock())
        peer = Peer(ws, 'host', 'g1')
        await peer.start_sender()
        mgr = ConnectionManager()

        raw = '{"t": 1, "d": {}}'
        await mgr.handle_message(peer, raw)
        await asyncio.sleep(0.05)
        assert ws.send_text.called

        await peer.close()

    @pytest.mark.asyncio
    async def test_parse_error(self):
        ws = MagicMock(send_text=AsyncMock())
        peer = Peer(ws, 'host', 'g1')
        await peer.start_sender()
        mgr = ConnectionManager()

        await mgr.handle_message(peer, 'not json')
        await asyncio.sleep(0.05)
        assert ws.send_text.called

        await peer.close()

    @pytest.mark.asyncio
    async def test_seq_duplicate_input(self):
        ws = MagicMock(send_text=AsyncMock())
        peer = Peer(ws, 'host', 'g1')
        await peer.start_sender()
        mgr = ConnectionManager()

        raw = '{"t": 4, "seq": 42, "d": {"type": "move"}}'
        await mgr.handle_message(peer, raw)
        await asyncio.sleep(0.05)

        peer.mark_seq_processed(42)
        await mgr.handle_message(peer, raw)
        await asyncio.sleep(0.05)

        await peer.close()


class TestViewFilter:
    def test_no_filter_without_opponent_key(self):
        result = filter_state_for_role({'a': 1}, 'host')
        assert result == {'a': 1}

    def test_filter_ai_is_new_placement_host(self):
        state = {
            'ai': {
                'board': [
                    {'uid': 1, 'is_new_placement': True},
                    {'uid': 2},
                    None,
                ]
            }
        }
        result = filter_state_for_role(state, 'host')
        ai_board = result['ai']['board']
        assert ai_board[0].get('is_new_placement') is None
        assert ai_board[1].get('is_new_placement') is None  # was None, stays None

    def test_filter_player_is_new_placement_guest(self):
        state = {
            'player': {
                'board': [
                    {'uid': 1, 'is_new_placement': True},
                ]
            }
        }
        result = filter_state_for_role(state, 'guest')
        assert result['player']['board'][0].get('is_new_placement') is None

    def test_filter_does_not_strip_own_side(self):
        state = {
            'player': {
                'board': [
                    {'uid': 1, 'is_new_placement': True},
                ]
            },
            'ai': {
                'board': []
            }
        }
        result = filter_state_for_role(state, 'host')
        # host sees player's own is_new_placement
        assert result['player']['board'][0]['is_new_placement'] is True

    def test_filter_non_dict_board_entry(self):
        state = {'ai': {'board': ['not_a_dict']}}
        result = filter_state_for_role(state, 'host')
        assert result['ai']['board'][0] == 'not_a_dict'
