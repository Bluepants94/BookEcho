import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.services.auth import bootstrap_admin
from app.services.settings_service import get_or_create_settings

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_path.mkdir(parents=True, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        bootstrap_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
@app.get(f"{settings.api_prefix}/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
