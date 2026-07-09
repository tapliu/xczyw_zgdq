from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..backend.room import (
    create_room, join_room, leave_room, set_ready, start_game,
    list_rooms, get_room, verify_room_access
)

router = APIRouter(prefix='/room')


class CreateRoomRequest(BaseModel):
    use_custom_generals: bool = True


class JoinRoomRequest(BaseModel):
    room_id: str
    token: str = ''  # not used for join, returned on success


class LeaveRoomRequest(BaseModel):
    room_id: str
    token: str


class StartGameRequest(BaseModel):
    room_id: str
    token: str


class RoomActionRequest(BaseModel):
    room_id: str
    token: str


@router.post('/create')
def api_create_room(body: CreateRoomRequest):
    room_id, host_token = create_room(body.use_custom_generals)
    return {'room_id': room_id, 'host_token': host_token}


@router.post('/join')
def api_join_room(body: JoinRoomRequest):
    guest_token = join_room(body.room_id)
    if not guest_token:
        raise HTTPException(status_code=400, detail='房间不存在或已满')
    return {'room_id': body.room_id, 'guest_token': guest_token}


@router.post('/leave')
def api_leave_room(body: LeaveRoomRequest):
    ok = leave_room(body.room_id, body.token)
    if not ok:
        raise HTTPException(status_code=400, detail='操作失败')
    return {'ok': True}


@router.post('/start')
def api_start_game(body: StartGameRequest):
    game_id = start_game(body.room_id, body.token)
    if not game_id:
        raise HTTPException(status_code=400, detail='无法开始游戏：房主身份不符、缺少对手或未准备就绪')
    return {'game_id': game_id, 'countdown': 5}


@router.get('/list')
def api_list_rooms():
    return {'rooms': list_rooms()}


@router.post('/ready')
def api_room_ready(body: RoomActionRequest):
    result = set_ready(body.room_id, body.token)
    if not result:
        raise HTTPException(status_code=400, detail='操作失败')
    return result


@router.post('/status')
def api_room_status(body: RoomActionRequest):
    room = verify_room_access(body.room_id, body.token)
    if not room:
        raise HTTPException(status_code=403, detail='无权访问')
    return room.to_dict()
