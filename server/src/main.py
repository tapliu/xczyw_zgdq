import os
import mimetypes
import logging
import asyncio
import time
import contextlib

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .routes.game import router as game_router, games
from .routes.room import router as room_router
from .network import (
    ConnectionManager, BattleSession,
    validate_ws_token, register_connection, unregister_connection,
)
from .network.protocol import C2S, S2C, parse_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('server')

mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('audio/mp4', '.m4a')


class CacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.endswith(('.webp', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff2', '.css', '.js', '.m4a')):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response


# ── Global Services ────────────────────────────────────────────────────

ws_manager = ConnectionManager()
battle_sessions: dict[str, BattleSession] = {}


def get_battle_session(game_id: str) -> BattleSession:
    if game_id not in battle_sessions:
        session = BattleSession(
            game_id=game_id,
            manager=ws_manager,
            state_getter=lambda gid: games.get(gid),
            state_setter=lambda gid, st: games.update({gid: st}),
        )
        battle_sessions[game_id] = session
    return battle_sessions[game_id]


# ── Lifespan ───────────────────────────────────────────────────────────

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    yield
    heartbeat_task.cancel()
    for bs in battle_sessions.values():
        await bs.stop()
    battle_sessions.clear()


async def _heartbeat_loop():
    while True:
        await asyncio.sleep(15)
        try:
            ws_manager.heartbeat_check()
        except Exception:
            logger.exception('heartbeat_check failed')


app = FastAPI(title="战国夺旗", lifespan=lifespan)


# ── HTTP Exception Handlers ────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc):
    errors = exc.errors() if hasattr(exc, 'errors') else [{'msg': str(exc)}]
    detail = '; '.join(e['msg'] for e in errors)
    return JSONResponse(status_code=422, content={'detail': detail})


app.add_middleware(CacheMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game_router, prefix="/api")
app.include_router(room_router, prefix="/api")

music_dir = os.path.join(os.path.dirname(__file__), 'data', 'music')
if os.path.isdir(music_dir):
    app.mount("/music", StaticFiles(directory=music_dir), name="music")

static_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'game')
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")


# ── WebSocket Endpoint ─────────────────────────────────────────────────

@app.websocket('/ws/{game_id}/{role}')
async def websocket_endpoint(ws: WebSocket, game_id: str, role: str):
    # ── Step 1: Basic parameter validation (before accept) ──────────────
    if role not in ('host', 'guest'):
        await ws.close(code=4001, reason='invalid role')
        return

    game = games.get(game_id)
    if not game:
        await ws.close(code=4004, reason='game not found')
        return

    # ── Step 2: Token authentication (before accept) ────────────────────
    token = ws.query_params.get('token', '')
    valid, reason = validate_ws_token(game_id, role, token)
    if not valid:
        logger.warning(f'[WS] Auth rejected: {role}@{game_id} — {reason}')
        await ws.close(code=4003, reason=reason)
        return

    # ── Step 3: Duplicate connection prevention (before accept) ─────────
    if not register_connection(game_id, role, token):
        await ws.close(code=4002, reason='重复连接：该角色已在线')
        return

    # ── Step 4: Accept handshake ────────────────────────────────────────
    await ws.accept()
    peer = ws_manager.register(game_id, role, ws)
    await peer.start_sender()

    await peer.send(S2C.PHASE, {
        'phase': game.game_phase,
        'round': game.round,
        'role': role,
    })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = parse_message(raw)
            except (ValueError, Exception) as e:
                await peer.send(S2C.ERROR, {'message': f'Parse error: {e}'})
                continue

            t = msg['t']
            data = msg['d']
            seq = msg['seq']
            tick = msg.get('tick', 0)

            if t in (C2S.HEARTBEAT, C2S.PING, C2S.LEAVE):
                await ws_manager.handle_message(peer, raw)
                if t == C2S.LEAVE:
                    break

            elif t == C2S.JOIN_BATTLE:
                session = get_battle_session(game_id)
                await session.start()
                snapshot = game.to_dict()
                await peer.send(S2C.STATE, {
                    'full': True,
                    'snapshot': snapshot,
                    'tick': 0,
                    'final': False,
                })

            elif t == C2S.SNAPSHOT_REQ:
                session = get_battle_session(game_id)
                await session.handle_snapshot_request(peer, data)

            elif t == C2S.INPUT:
                await ws_manager.handle_message(peer, raw)
                if game.game_phase in ('battle', 'multiplayer_place'):
                    session = get_battle_session(game_id)
                    session.enqueue_input(peer, data, seq, tick=tick)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f'[WS] Error: {e}', exc_info=True)
    finally:
        ws_manager.unregister(game_id, role)
        unregister_connection(game_id, role)
        bs = battle_sessions.get(game_id)
        if bs:
            peers = ws_manager.get_peers(game_id)
            if not peers:
                await bs.stop()
                battle_sessions.pop(game_id, None)


# ── Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("server.src.main:app", host="127.0.0.1", port=8000, reload=True)
