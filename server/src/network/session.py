"""
Battle Session — Logic Layer
==============================
Layer 3: tick loop, input queue with tick alignment,
         delta state sync, reconnection snapshots.
Layer 4: delegates to backend/state.py for rule enforcement.
"""

import asyncio
import logging
import time
from typing import Callable, Optional

from .connection import ConnectionManager, Peer, filter_state_for_role
from .protocol import (
    C2S, S2C, InputOp, compute_delta,
    INPUT_QUEUE_WARN, INPUT_QUEUE_DROP, should_drop_input,
)

logger = logging.getLogger(__name__)

BATTLE_TICK_RATE = 10
BATTLE_TICK_INTERVAL = 1.0 / BATTLE_TICK_RATE
MAX_INPUTS_PER_TICK = 64
DELTA_SYNC_INTERVAL = 5          # full → delta after this many ticks
SNAPSHOT_HISTORY_LEN = 60        # keep 6 seconds of snapshots (at 10 Hz)


class BattleSession:
    """
    Real-time battle session for one game.

    Lifecycle:
      1. Created when both players join via WebSocket (JOIN_BATTLE).
      2. Runs tick loop during battle phases.
      3. Validates → applies client inputs at the correct tick.
      4. Broadcasts delta or full state snapshots.
      5. Stores recent snapshots for reconnection recovery.
      6. Destroyed when battle phase ends or both disconnect.
    """

    def __init__(self, game_id: str, manager: ConnectionManager,
                 state_getter: Callable, state_setter: Callable):
        self.game_id = game_id
        self.manager = manager
        self._get_state = state_getter
        self._set_state = state_setter

        self.input_queue: list[dict] = []
        self._tick_task: Optional[asyncio.Task] = None
        self._running = False
        self._tick_count = 0

        # ── Snapshot history for reconnection ────────────────────────
        self._snapshot_history: list[dict] = []

        # ── Previous full state dict for delta computation ───────────
        self._last_full_dict: Optional[dict] = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info(f'[Session] Battle {self.game_id} started')

    async def stop(self):
        self._running = False
        if self._tick_task:
            self._tick_task.cancel()
            self._tick_task = None
        self._snapshot_history.clear()
        self._last_full_dict = None
        logger.info(f'[Session] Battle {self.game_id} stopped')

    def enqueue_input(self, peer: Peer, data: dict, seq: int, tick: int = 0):
        """Add an input to the queue, stamped with the target tick.
        Drops the input if the queue is beyond the drop watermark.
        """
        if should_drop_input(len(self.input_queue)):
            # Queue overwhelmed — drop and let client retry via ACK loss
            peer.unacked_count = max(0, peer.unacked_count - 1)
            return
        self.input_queue.append({
            'role': peer.role,
            'seq': seq,
            'tick': tick,
            'data': data,
        })
        peer.input_seq = seq
        peer.mark_seq_processed(seq)

    def get_snapshot(self, tick: Optional[int] = None) -> Optional[dict]:
        """Return a past snapshot for reconnection (closest to requested tick)."""
        if not self._snapshot_history:
            return None
        if tick is None:
            return self._snapshot_history[-1]
        best = self._snapshot_history[-1]
        for snap in reversed(self._snapshot_history):
            if abs(snap.get('tick', 0) - tick) < abs(best.get('tick', 0) - tick):
                best = snap
        return best

    # ── Tick Loop ──────────────────────────────────────────────────────

    async def _tick_loop(self):
        while self._running:
            tick_start = asyncio.get_event_loop().time()
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'[Session] Tick error: {e}', exc_info=True)

            elapsed = asyncio.get_event_loop().time() - tick_start
            sleep_time = max(0, BATTLE_TICK_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)

    async def _tick(self):
        state = self._get_state(self.game_id)
        if state is None:
            await self.stop()
            return

        # 1. Drain input queue (up to MAX)
        inputs = self.input_queue[:MAX_INPUTS_PER_TICK]
        self.input_queue = self.input_queue[MAX_INPUTS_PER_TICK:]

        # 2. Filter inputs for this tick
        for inp in inputs:
            if inp.get('tick') and inp['tick'] != self._tick_count:
                # Future/past tick — re-queue or drop
                if inp['tick'] > self._tick_count:
                    # Re-queue for later
                    if len(self.input_queue) < 1000:
                        self.input_queue.append(inp)
                continue

        # 3. Validate & apply inputs
        for inp in inputs:
            if inp.get('tick') and inp['tick'] != self._tick_count:
                continue
            await self._process_input(state, inp)

        # 4. Backpressure: monitor queue depth and push flow control
        backlog = len(self.input_queue)
        if backlog >= INPUT_QUEUE_WARN:
            await self.manager.send_flow_control(self.game_id, backlog)
        else:
            # Pressure relieved — reset for any peer that had backpressure
            for peer in self.manager.get_peers(self.game_id).values():
                if peer.last_backpressure and peer.alive:
                    await self.manager.send_flow_control_to_peer(peer, 0)

        # 5. Run AI auto-advance
        self._advance_ai(state)

        # 6. Persist state
        self._set_state(self.game_id, state)

        # 7. Broadcast state sync
        await self._sync_state(state)

        self._tick_count += 1

    async def _process_input(self, state, inp: dict):
        """Validate + apply one input, send ACK or ERROR."""
        result = self._validate_input(state, inp)
        sender = self.manager.get_peer(self.game_id, inp['role'])

        # Decrement unacked count for this peer now that the seq is consumed
        if sender:
            sender.unacked_count = max(0, sender.unacked_count - 1)

        if not result['valid']:
            if sender and sender.alive:
                await sender.send(S2C.ERROR, {
                    'seq': inp['seq'],
                    'message': result.get('error', 'invalid'),
                    'tick': self._tick_count,
                })
            return

        event = self._apply_input(state, inp)
        if sender and sender.alive:
            await sender.send(S2C.ACK, {
                'seq': inp['seq'],
                'tick': self._tick_count,
            })
        if event:
            await self.manager.broadcast(self.game_id, S2C.EVENT, event)

    async def _sync_state(self, state):
        """Send delta or full state to both peers, with view filtering."""
        if state.game_phase not in ('battle', 'multiplayer_place'):
            final = state.to_dict()
            await self._broadcast_state(final, final=True)
            await self.stop()
            return

        full = state.to_dict()

        # Store snapshot for reconnection
        self._snapshot_history.append({
            'snapshot': full,
            'tick': self._tick_count,
        })
        if len(self._snapshot_history) > SNAPSHOT_HISTORY_LEN:
            self._snapshot_history.pop(0)

        # Decide full vs delta
        send_full = (self._last_full_dict is None or
                     self._tick_count % DELTA_SYNC_INTERVAL == 0)

        if send_full:
            self._last_full_dict = full
            for role, peer in self.manager.get_peers(self.game_id).items():
                if not peer.alive:
                    continue
                filtered = filter_state_for_role(full, role)
                await peer.send(S2C.STATE, {
                    'full': True,
                    'snapshot': filtered,
                    'tick': self._tick_count,
                    'final': False,
                })
        else:
            delta = compute_delta(self._last_full_dict, full)
            self._last_full_dict = full
            if delta:  # only send if something changed
                for role, peer in self.manager.get_peers(self.game_id).items():
                    if not peer.alive:
                        continue
                    filtered_delta = filter_state_for_role(delta, role)
                    await peer.send(S2C.STATE, {
                        'full': False,
                        'delta': filtered_delta,
                        'tick': self._tick_count,
                        'base_tick': self._tick_count - DELTA_SYNC_INTERVAL,
                        'final': False,
                    })

    async def _broadcast_state(self, full: dict, final: bool = False):
        """Broadcast a full state (for phase end)."""
        for role, peer in self.manager.get_peers(self.game_id).items():
            if not peer.alive:
                continue
            filtered = filter_state_for_role(full, role)
            await peer.send(S2C.STATE, {
                'full': True,
                'snapshot': filtered,
                'tick': self._tick_count,
                'final': final,
            })

    # ── Reconnection ─────────────────────────────────────────────────

    async def handle_snapshot_request(self, peer: Peer, data: dict):
        """Send the closest stored snapshot to a reconnecting client."""
        tick = data.get('tick')
        snap = self.get_snapshot(tick)
        if snap:
            filtered = filter_state_for_role(snap['snapshot'], peer.role)
            await peer.send(S2C.SNAPSHOT_RES, {
                'snapshot': filtered,
                'tick': snap['tick'],
                'current_tick': self._tick_count,
            })
        else:
            # No history — send current state
            state = self._get_state(self.game_id)
            if state:
                full = state.to_dict()
                filtered = filter_state_for_role(full, peer.role)
                await peer.send(S2C.SNAPSHOT_RES, {
                    'snapshot': filtered,
                    'tick': 0,
                    'current_tick': self._tick_count,
                })
            else:
                await peer.send(S2C.ERROR, {'message': 'state not found'})

    # ── Input Validation ────────────────────────────────────────────

    def _validate_input(self, state, inp: dict) -> dict:
        op = inp['data'].get('type')
        role = inp['role']
        side = state.player if role == 'host' else state.ai
        board = side.board

        if op == InputOp.MOVE:
            unit_uid = inp['data'].get('unit_uid')
            to_cell = inp['data'].get('to_cell')
            if unit_uid is None or to_cell is None:
                return {'valid': False, 'error': 'missing unit_uid or to_cell'}
            if not (0 <= to_cell < 64):
                return {'valid': False, 'error': 'to_cell out of range'}

            unit = None
            from_cell = None
            for i, u in enumerate(board):
                if u and u.uid == unit_uid:
                    unit = u
                    from_cell = i
                    break
            if unit is None:
                return {'valid': False, 'error': 'unit not found'}
            if unit.pinned:
                return {'valid': False, 'error': 'unit is pinned'}
            if not state._is_active_cell(to_cell):
                return {'valid': False, 'error': 'target cell is locked'}
            if state.player.board[to_cell] or state.ai.board[to_cell]:
                return {'valid': False, 'error': 'target cell occupied'}

            fr, fc = divmod(from_cell, 8)
            tr, tc = divmod(to_cell, 8)
            if role == 'host':
                if not (tr == fr - 1 and abs(tc - fc) <= 1):
                    return {'valid': False, 'error': 'invalid move target'}
            else:
                if not (tr == fr + 1 and abs(tc - fc) <= 1):
                    return {'valid': False, 'error': 'invalid move target'}
            return {'valid': True}

        elif op == InputOp.ATTACK:
            unit_uid = inp['data'].get('unit_uid')
            target_uid = inp['data'].get('target_uid')
            if unit_uid is None or target_uid is None:
                return {'valid': False, 'error': 'missing unit_uid or target_uid'}
            attacker = None
            for u in board:
                if u and u.uid == unit_uid:
                    attacker = u
                    break
            if attacker is None:
                return {'valid': False, 'error': 'attacker not found'}
            if attacker.pinned:
                return {'valid': False, 'error': 'attacker is pinned'}
            opp_side = state.ai if role == 'host' else state.player
            target = None
            for u in opp_side.board:
                if u and u.uid == target_uid:
                    target = u
                    break
            if target is None:
                return {'valid': False, 'error': 'target not found'}
            return {'valid': True}

        elif op == InputOp.HOLD:
            unit_uid = inp['data'].get('unit_uid')
            unit = None
            for u in board:
                if u and u.uid == unit_uid:
                    unit = u
                    break
            if unit is None:
                return {'valid': False, 'error': 'unit not found'}
            return {'valid': True}

        return {'valid': False, 'error': f'unknown operation: {op}'}

    # ── Input Application ───────────────────────────────────────────

    def _apply_input(self, state, inp: dict) -> Optional[dict]:
        op = inp['data'].get('type')
        role = inp['role']
        side = state.player if role == 'host' else state.ai
        board = side.board
        opp_board = state.ai.board if role == 'host' else state.player.board

        if op == InputOp.MOVE:
            unit_uid = inp['data']['unit_uid']
            to_cell = inp['data']['to_cell']
            from_cell = None
            for i, u in enumerate(board):
                if u and u.uid == unit_uid:
                    from_cell = i
                    break
            if from_cell is not None:
                board[to_cell] = board[from_cell]
                board[from_cell] = None
                return {
                    'type': 'moved',
                    'unit_uid': unit_uid,
                    'from_cell': from_cell,
                    'to_cell': to_cell,
                    'role': role,
                }

        elif op == InputOp.ATTACK:
            unit_uid = inp['data']['unit_uid']
            target_uid = inp['data']['target_uid']

            a_cell = next((i for i, u in enumerate(board) if u and u.uid == unit_uid), None)
            t_cell = next((i for i, u in enumerate(opp_board) if u and u.uid == target_uid), None)
            if a_cell is None or t_cell is None:
                return None

            ar, ac = divmod(a_cell, 8)
            tr, tc = divmod(t_cell, 8)
            if abs(ar - tr) <= 1 and abs(ac - tc) <= 1:
                result = state.resolve_rt_melee(unit_uid, target_uid, role == 'host')
                if result:
                    return {
                        'type': 'attacked',
                        'attacker_uid': unit_uid,
                        'target_uid': target_uid,
                        'damage_dealt': result['target_damage'],
                        'damage_taken': result['attacker_damage'],
                        'attacker_alive': result['attacker_alive'],
                        'target_alive': result['target_alive'],
                        'role': role,
                    }

        elif op == InputOp.HOLD:
            return {
                'type': 'hold',
                'unit_uid': inp['data']['unit_uid'],
                'role': role,
            }

        return None

    def _advance_ai(self, state):
        """Auto-advance AI units during battle phase."""
        if state.game_phase != 'battle':
            return
        pass
