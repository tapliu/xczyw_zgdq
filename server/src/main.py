import os
import mimetypes
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from .routes.game import router as game_router
from .routes.room import router as room_router

# Register MIME types that Python's mimetypes doesn't know or gets wrong
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('audio/mp4', '.m4a')

class CacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.endswith(('.webp', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff2', '.css', '.js', '.m4a')):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response

app = FastAPI(title="战国夺旗")

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

if __name__ == "__main__":
    uvicorn.run("server.src.main:app", host="127.0.0.1", port=8000, reload=True)
