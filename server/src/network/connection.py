"""
Connection Manager — Network Layer
====================================
WebSocket connection lifecycle, heartbeat, send queue, rate limiter,
seq sliding window, and view filtering.
"""

import asyncio
import json
import logging
import time
from typing import Callable, Optional

from .protocol import (
    C2S, S2C, SEQ_WINDOW_SIZE, MAX_UNACKED, SEND_QUEUE_WARN, SEND_QUEUE_DROP,
    make_message, parse_message, validate_message, calc_allow_rate,
)

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15.0
HEARTBEAT_TIMEOUT = 45.0
RATE_LIMIT_WINDOW = 1.0          # 1 second window
RATE_LIMIT_MAX_INPUTS = 30       # max inputs per peer per window


class Peer:
    """A connected WebSocket client with send queue, seq guard, and rate limiter."""

    def __init__(self, ws, role: str, game_id: str):
        self.ws = ws
        self.role = role          # 'host' | 'guest'
        self.game_id = game_id
        self.last_heartbeat = time.time()
        self.input_seq = 0        # last acknowledged seq
        self.alive = True

        # ── Seq sliding window ──────────────────────────────────────
        self.processed_seqs = set()
        self.seq_window_start = 0
        self.unacked_count = 0       # inputs received but not yet processed this tick

        # ── Send queue (async channel to avoid concurrent write) ────
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._sender_task: Optional[asyncio.Task] = None

        # ── Rate limiter ────────────────────────────────────────────
        self._rate_tokens = RATE_LIMIT_MAX_INPUTS
        self._rate_last_refill = time.time()

        # ── Backpressure state ──────────────────────────────────────
        self.last_backpressure = False    # last sent backpressure flag
        self.current_allow_rate = RATE_LIMIT_MAX_INPUTS

    # ── Async Send Queue ─────────────────────────────────────────────

    async def start_sender(self):
        """Launch background task that drains the send queue."""
        if self._sender_task is not None:
            return
        self._sender_task = asyncio.create_task(self._sender_loop())

    async def stop_sender(self):
        if self._sender_task:
            self._sender_task.cancel()
            self._sender_task = None

    async def _sender_loop(self):
        while self.alive:
            try:
                text = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                await self.ws.send_text(text)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                self.alive = False
                break

    async def send(self, msg_type: int, data: dict, seq: int = 0, tick: int = 0):
        """Enqueue a message for async sending."""
        if not self.alive:
            return
        text = make_message(msg_type, data, seq=seq, tick=tick)
        await self._send_queue.put(text)

    async def send_json(self, obj: dict):
        """Enqueue a raw JSON dict as a message."""
        if not self.alive:
            return
        await self._send_queue.put(json.dumps(obj, ensure_ascii=False))

    # ── Send Queue Depth ────────────────────────────────────────────

    def get_send_queue_depth(self) -> int:
        """Approximate number of messages waiting in the send queue."""
        return self._send_queue.qsize() if hasattr(self._send_queue, 'qsize') else 0

    # ── Backpressure ─────────────────────────────────────────────────

    def update_backpressure_state(self, backlog: int):
        """Recalculate allowed rate based on server-side input queue backlog."""
        self.current_allow_rate = calc_allow_rate(backlog)
        self.last_backpressure = backlog >= SEND_QUEUE_WARN

    def check_unacked_limit(self) -> bool:
        """True if client has too many unacknowledged inputs."""
        return self.unacked_count >= MAX_UNACKED

    # ── Seq Sliding Window ───────────────────────────────────────────

    def is_seq_duplicate(self, seq: int) -> bool:
        """True if seq has already been processed."""
        if seq in self.processed_seqs:
            return True
        # Reject expired seqs (before window start)
        if seq < self.seq_window_start:
            return True
        return False

    def mark_seq_processed(self, seq: int):
        """Record seq and slide window."""
        self.processed_seqs.add(seq)
        # Prune old entries
        while self.seq_window_start <= seq - SEQ_WINDOW_SIZE:
            self.seq_window_start += 1
            self.processed_seqs.discard(self.seq_window_start - 1)

    # ── Rate Limiter ─────────────────────────────────────────────────

    def rate_limit_input(self) -> bool:
        """True if input is allowed, False if rate-limited."""
        now = time.time()
        elapsed = now - self._rate_last_refill
        if elapsed >= RATE_LIMIT_WINDOW:
            self._rate_tokens = RATE_LIMIT_MAX_INPUTS
            self._rate_last_refill = now
        if self._rate_tokens <= 0:
            return False
        self._rate_tokens -= 1
        return True

    # ── Cleanup ──────────────────────────────────────────────────────

    async def close(self):
        self.alive = False
        await self.stop_sender()


# ── View Filtering ─────────────────────────────────────────────────────

def filter_state_for_role(state_dict: dict, role: str) -> dict:
    """
    Strip opponent-sensitive data per role.
    - Remove `is_new_placement` flags from opponent's field.
    - Future: remove fog-of-war cells.
    """
    filtered = dict(state_dict)
    if role == 'host':
        side_key = 'ai'
    else:
        side_key = 'player'
    opponent = filtered.get(side_key)
    if isinstance(opponent, dict):
        board = opponent.get('board', [])
        for u in board:
            if isinstance(u, dict):
                u.pop('is_new_placement', None)
    return filtered


# ── Connection Manager ─────────────────────────────────────────────────

class ConnectionManager:
    """
    Manages all active WebSocket peers.

    Maps: game_id -> {host: Peer, guest: Peer}
    """

    def __init__(self):
        self._games: dict[str, dict[str, Peer]] = {}

    def register(self, game_id: str, role: str, ws) -> Peer:
        peer = Peer(ws, role, game_id)
        self._games.setdefault(game_id, {})[role] = peer
        logger.info(f'[WS] {role} joined game {game_id}')
        return peer

    def unregister(self, game_id: str, role: str):
        peers = self._games.get(game_id)
        if peers:
            peer = peers.pop(role, None)
            if peer:
                asyncio.ensure_future(peer.close())
            if not peers:
                del self._games[game_id]
        logger.info(f'[WS] {role} left game {game_id}')

    def get_peer(self, game_id: str, role: str) -> Optional[Peer]:
        peers = self._games.get(game_id)
        if peers:
            return peers.get(role)
        return None

    def get_peers(self, game_id: str) -> dict[str, Peer]:
        return self._games.get(game_id, {})

    async def broadcast(self, game_id: str, msg_type: int, data: dict,
                        exclude_role: str = None):
        for role, peer in self.get_peers(game_id).items():
            if role == exclude_role or not peer.alive:
                continue
            await peer.send(msg_type, data)

    async def send_to_role(self, game_id: str, role: str, msg_type: int,
                           data: dict, seq: int = 0):
        peer = self.get_peer(game_id, role)
        if peer and peer.alive:
            await peer.send(msg_type, data, seq=seq)

    # ── Message Ingress ──────────────────────────────────────────────

    async def handle_message(self, peer: Peer, raw: str):
        """Route an incoming message — validates framing, seq guard, rate, then dispatch."""
        try:
            msg = parse_message(raw)
        except (ValueError, json.JSONDecodeError) as e:
            await peer.send(S2C.ERROR, {'message': f'Parse error: {e}'})
            return

        t = msg['t']
        data = msg['d']
        seq = msg['seq']

        # ── Structural validation ─────────────────────────────────────
        err = validate_message(t, data)
        if err:
            await peer.send(S2C.ERROR, {'message': err, 'seq': seq})
            return

        # ── Seq dedup + flow control (only for INPUT) ─────────────────
        if t == C2S.INPUT:
            if peer.is_seq_duplicate(seq):
                await peer.send(S2C.ACK, {'seq': seq, 'tick': msg.get('tick', 0)})
                return
            # Seq-based flow control: too many unacknowledged
            if peer.check_unacked_limit():
                peer.unacked_count += 1  # still count it so client can't bypass
                await peer.send(S2C.ERROR, {
                    'message': 'backpressure: reduce input rate',
                    'seq': seq,
                })
                return
            # Rate limit inputs
            if not peer.rate_limit_input():
                await peer.send(S2C.ERROR, {'message': 'rate limited', 'seq': seq})
                return
            peer.unacked_count += 1

        # ── Heartbeat / Ping ──────────────────────────────────────────
        if t == C2S.HEARTBEAT or t == C2S.PING:
            peer.last_heartbeat = time.time()
            await peer.send(S2C.PONG if t == C2S.PING else S2C.HEARTBEAT, {})

        elif t == C2S.LEAVE:
            self.unregister(peer.game_id, peer.role)

    # ── Backpressure Notification ────────────────────────────────────

    async def send_flow_control(self, game_id: str, backlog: int):
        """Push S2C.FLOW_CONTROL to all connected peers."""
        for role, peer in self.get_peers(game_id).items():
            if not peer.alive:
                continue
            peer.update_backpressure_state(backlog)
            await peer.send(S2C.FLOW_CONTROL, {
                'queue_backlog': backlog,
                'allow_rate': peer.current_allow_rate,
                'backpressure': peer.last_backpressure,
            })

    async def send_flow_control_to_peer(self, peer: Peer, backlog: int):
        """Push FLOW_CONTROL to a single peer."""
        peer.update_backpressure_state(backlog)
        await peer.send(S2C.FLOW_CONTROL, {
            'queue_backlog': backlog,
            'allow_rate': peer.current_allow_rate,
            'backpressure': peer.last_backpressure,
        })

        # C2S.INPUT, C2S.JOIN_BATTLE, C2S.SNAPSHOT_REQ → handled by session

    # ── Heartbeat Check ──────────────────────────────────────────────

    async def heartbeat_check(self):
        now = time.time()
        for game_id, peers in list(self._games.items()):
            for role, peer in list(peers.items()):
                if now - peer.last_heartbeat > HEARTBEAT_TIMEOUT:
                    logger.warning(f'[WS] {role} in {game_id} timed out')
                    peer.alive = False
                    self.unregister(game_id, role)
