"""
Auth Service — WebSocket Handshake Authentication
====================================================
Validates tokens in the WS handshake phase (before accept()),
tracks active connections to prevent duplicate WS per token,
and provides clear rejection reasons.

Design:
  - Token is stored on GameState (host_token / guest_token) when
    a multiplayer game starts from a room.
  - Validation: look up game by game_id, compare token + role.
  - Active connections are tracked per (game_id, role) to prevent
    duplicate WS sessions with the same credentials.
  - All state is held in-memory (no persistence needed).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Active Connection Tracking ─────────────────────────────────────────
# Keyed by (game_id, role) -> token to prevent duplicates.
_active_connections: dict[tuple[str, str], str] = {}


def validate_ws_token(game_id: str, role: str, token: str) -> tuple[bool, str]:
    """
    Validate WebSocket handshake token.

    Returns:
        (True, '') on success
        (False, reason) on failure — reason is a human-readable message
          suitable for logging / close reason.
    """
    if not token:
        return False, '缺少令牌'

    if role not in ('host', 'guest'):
        return False, '无效角色'

    # Lazy import to avoid circular dependency at module load time.
    from ..routes.game import games
    game = games.get(game_id)
    if game is None:
        return False, '游戏不存在'

    # Compare token against the correct slot for this role.
    expected = game.host_token if role == 'host' else game.guest_token
    if not expected:
        return False, f'游戏未配置{role}令牌'

    if token != expected:
        return False, '令牌不匹配'

    return True, ''


def register_connection(game_id: str, role: str, token: str) -> bool:
    """
    Register an active WS connection.

    Returns True if registration succeeds, False if a connection for
    (game_id, role) is already active (duplicate).
    """
    key = (game_id, role)
    if key in _active_connections:
        existing_token = _active_connections[key]
        if existing_token != token:
            # Different token → reject (shouldn't happen in practice,
            # but guards against token confusion).
            logger.warning(f'[Auth] Connection collision: {game_id}/{role} '
                           f'registered with different token')
            return False
        # Same token already connected → duplicate WS
        logger.warning(f'[Auth] Duplicate WS connection rejected: '
                       f'{game_id}/{role}')
        return False
    _active_connections[key] = token
    logger.info(f'[Auth] {role} connected to game {game_id}')
    return True


def unregister_connection(game_id: str, role: str):
    """Remove a WS connection from the active set."""
    key = (game_id, role)
    prev = _active_connections.pop(key, None)
    if prev is not None:
        logger.info(f'[Auth] {role} disconnected from game {game_id}')


def get_active_connections(game_id: str) -> dict[str, str]:
    """Return {role: token} for all active connections in a game."""
    return {
        role: token
        for (gid, role), token in _active_connections.items()
        if gid == game_id
    }


def clear_game(game_id: str):
    """Remove all active connections for a game (e.g. on session end)."""
    keys = [k for k in _active_connections if k[0] == game_id]
    for k in keys:
        del _active_connections[k]
