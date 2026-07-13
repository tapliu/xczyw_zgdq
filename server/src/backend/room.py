import uuid
import threading
from typing import Optional
from .state import GameState

class Room:
    def __init__(self, room_id: str, host_token: str, use_custom_generals: bool):
        self.room_id = room_id
        self.host_token = host_token
        self.guest_token: Optional[str] = None
        self.game_id: Optional[str] = None
        self.status = 'waiting'
        self.use_custom_generals = use_custom_generals
        self.countdown = 0
        self.host_ready = False
        self.guest_ready = False
        self.terrain = 'normal'

    @property
    def has_guest(self):
        return self.guest_token is not None

    @property
    def is_full(self):
        return self.has_guest

    def to_dict(self):
        return {
            'room_id': self.room_id,
            'has_guest': self.has_guest,
            'status': self.status,
            'game_id': self.game_id,
            'use_custom_generals': self.use_custom_generals,
            'host_ready': self.host_ready,
            'guest_ready': self.guest_ready,
            'terrain': self.terrain,
        }


_rooms: dict[str, Room] = {}
_lock = threading.Lock()


def create_room(use_custom_generals: bool, terrain: str = 'normal') -> tuple[str, str]:
    room_id = str(uuid.uuid4())[:8]
    host_token = str(uuid.uuid4())
    with _lock:
        room = Room(room_id, host_token, use_custom_generals)
        room.terrain = terrain
        _rooms[room_id] = room
    return room_id, host_token


def join_room(room_id: str) -> Optional[str]:
    with _lock:
        room = _rooms.get(room_id)
        if not room:
            return None
        if room.is_full:
            return None
        if room.status != 'waiting':
            return None
        guest_token = str(uuid.uuid4())
        room.guest_token = guest_token
    return guest_token


def leave_room(room_id: str, token: str) -> bool:
    with _lock:
        room = _rooms.get(room_id)
        if not room:
            return False
        if room.host_token == token:
            del _rooms[room_id]
            return True
        if room.guest_token == token:
            room.guest_token = None
            return True
    return False


def set_ready(room_id: str, token: str) -> Optional[dict]:
    with _lock:
        room = _rooms.get(room_id)
        if not room:
            return None
        if room.status != 'waiting':
            return None
        if room.host_token == token:
            room.host_ready = not room.host_ready
        elif room.guest_token == token:
            room.guest_ready = not room.guest_ready
        else:
            return None
        return room.to_dict()


def start_game(room_id: str, host_token: str) -> Optional[str]:
    with _lock:
        room = _rooms.get(room_id)
        if not room:
            return None
        if room.host_token != host_token:
            return None
        if not room.has_guest:
            return None
        if not room.host_ready or not room.guest_ready:
            return None
        if room.status != 'waiting':
            return None

        game_id = str(uuid.uuid4())
        game = GameState(game_id)
        game.multiplayer = True
        game.reset_game(include_custom_generals=room.use_custom_generals)
        game.set_terrain(room.terrain)
        # reset_game already called _init_draw_sequence(); multiplayer flag ensures host/guest roles
        game._log('多人对战开始', 'info')

        from ..routes.game import games
        games[game_id] = game

        room.game_id = game_id
        room.status = 'playing'
    return game_id


def set_room_terrain(room_id: str, token: str, terrain: str) -> bool:
    if terrain not in ('normal', 'nagashino', 'tennozan'):
        return False
    with _lock:
        room = _rooms.get(room_id)
        if not room:
            return False
        if room.host_token != token:
            return False
        if room.status != 'waiting':
            return False
        room.terrain = terrain
    return True


def list_rooms() -> list[dict]:
    with _lock:
        result = []
        for room in _rooms.values():
            if room.status == 'waiting' and not room.is_full:
                result.append(room.to_dict())
        return result


def get_room(room_id: str) -> Optional[Room]:
    return _rooms.get(room_id)


def verify_room_access(room_id: str, token: str) -> Optional[Room]:
    room = get_room(room_id)
    if not room:
        return None
    if room.host_token != token and room.guest_token != token:
        return None
    return room
