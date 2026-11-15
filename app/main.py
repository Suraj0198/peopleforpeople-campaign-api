"""PeopleforPeople Campaign API (ACS WIL Group 5). Run: uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .errors import register_error_handlers
from .routers import admin, campaigns
from . import models  # noqa: F401  (registers tables)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().auto_create_tables:
        Base.metadata.create_all(engine)  # creates only missing tables; never drops data
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PeopleforPeople Campaign API",
        version="1.0.0",
        description="Campaigns, small-business promotions and admin moderation (Jira KAN-23, KAN-31, KAN-40, KAN-49).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # needed so the browser sends the login cookie
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Dev-User"],
    )
    register_error_handlers(app)
    app.include_router(campaigns.router)
    app.include_router(admin.router)

    @app.get("/health", tags=["health"])
    def health():
        return {"ok": True, "auth_mode": settings.auth_mode}

    return app


app = create_app()
