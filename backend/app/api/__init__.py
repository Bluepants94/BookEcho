from fastapi import APIRouter

from app.api import admin, auth, books, playback, progress, tts

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(books.router)
api_router.include_router(progress.router)
api_router.include_router(playback.router)
api_router.include_router(tts.router)
api_router.include_router(admin.router)
