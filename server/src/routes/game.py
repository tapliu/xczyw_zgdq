import uuid
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..backend.state import GameState, edited_characters

router = APIRouter()

games = {}


class PlaceRequest(BaseModel):
    char_id: int
    cell: int
    troops: int


class TerrainRequest(BaseModel):
    terrain: str


class PickCardRequest(BaseModel):
    char_id: int


def get_game_or_404(game_id: str):
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail='Game not found')
    return game


@router.post('/game/new')
def new_game():
    game_id = str(uuid.uuid4())
    game = GameState(game_id)
    game.reset_game()
    games[game_id] = game
    return {'game_id': game_id, 'state': game.to_dict()}


@router.get('/game/{game_id}')
def get_game(game_id: str):
    game = get_game_or_404(game_id)
    return game.to_dict()


@router.post('/game/{game_id}/draw')
def draw_phase(game_id: str):
    game = get_game_or_404(game_id)
    if game.game_phase not in ('idle', 'draw'):
        raise HTTPException(status_code=400, detail='抽卡阶段才能抽卡')
    game.draw_phase()
    return {'state': game.to_dict()}


@router.post('/game/{game_id}/draw-options')
def draw_options(game_id: str):
    game = get_game_or_404(game_id)
    if game.game_phase not in ('idle', 'draw', 'pick_card'):
        raise HTTPException(status_code=400, detail='抽卡阶段才能抽卡')
    try:
        game.draw_options()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'state': game.to_dict(), 'options': game._pending_draw_options or []}


@router.post('/game/{game_id}/pick-card')
def pick_card(game_id: str, body: PickCardRequest):
    game = get_game_or_404(game_id)
    if game.game_phase != 'pick_card':
        raise HTTPException(status_code=400, detail='不在选卡阶段')
    try:
        game.pick_card(body.char_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'state': game.to_dict()}


@router.post('/game/{game_id}/place')
def place_unit(game_id: str, body: PlaceRequest):
    game = get_game_or_404(game_id)
    try:
        game.place_unit(body.char_id, body.cell, body.troops)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return game.to_dict()


@router.post('/game/{game_id}/end-turn')
def end_turn(game_id: str):
    game = get_game_or_404(game_id)
    if game.game_phase != 'place_player':
        raise HTTPException(status_code=400, detail='不在放置阶段')
    try:
        game.end_placement()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return game.to_dict()


@router.post('/game/{game_id}/auto-place')
def auto_place(game_id: str):
    game = get_game_or_404(game_id)
    try:
        game.auto_place_remaining()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return game.to_dict()


@router.post('/game/{game_id}/reset')
def reset_game(game_id: str):
    game = get_game_or_404(game_id)
    game.reset_game()
    return game.to_dict()


@router.post('/game/{game_id}/set-terrain')
def set_terrain(game_id: str, body: TerrainRequest):
    game = get_game_or_404(game_id)
    try:
        game.set_terrain(body.terrain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return game.to_dict()


# ---- Character Editor API (in-memory, does not touch characters.json) ----
class SaveCharactersRequest(BaseModel):
    characters: list[Dict[str, Any]]


@router.post('/characters/save')
def _recalc_rating(c):
    if c.get('leadership')==100 or c.get('martial')==100 or c.get('intelligence')==100 or c.get('politics')==100:
        return 'S+'
    return None

def save_characters(body: SaveCharactersRequest):
    # Recalculate ratings server-side
    splus_ids = set()
    for c in body.characters:
        r = _recalc_rating(c)
        if r == 'S+':
            splus_ids.add(c['id'])
    rest = [c for c in body.characters if c['id'] not in splus_ids]
    rest.sort(key=lambda c: -(c.get('leadership',0)+c.get('martial',0)+c.get('intelligence',0)+c.get('politics',0)))
    n = len(rest)
    ratios = [(1/11, 'S'), (3/11, 'A'), (5/11, 'B'), (8/11, 'C'), (1, 'D')]
    for i, c in enumerate(rest):
        p = i / n
        for thr, tier in ratios:
            if p < thr:
                c['rating'] = tier
                break
    for c in body.characters:
        if c['id'] in splus_ids:
            c['rating'] = 'S+'

    edited_characters.clear()
    for c in body.characters:
        cid = c.get('id')
        if cid is not None:
            edited_characters[cid] = c
    return {'saved': len(body.characters), 'ok': True}


@router.post('/characters/reset-all')
def reset_all_characters():
    edited_characters.clear()
    return {'ok': True}


@router.get('/characters/edited')
def get_edited_characters():
    return {'characters': list(edited_characters.values())}


# ---- Custom General API ----
from ..backend.state import custom_generals


class CustomGeneralRequest(BaseModel):
    generals: list[Dict[str, Any]]


@router.post('/characters/custom/save')
def save_custom_generals(body: CustomGeneralRequest):
    custom_generals.clear()
    for g in body.generals:
        gid = g.get('id')
        if gid is not None:
            custom_generals[gid] = g
    return {'saved': len(body.generals), 'ok': True}


@router.get('/characters/custom')
def get_custom_generals():
    return {'generals': list(custom_generals.values())}
