import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.base_class import Base
from app.db.session import engine, SessionLocal
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
import app.models  

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):

    if settings.ENV != "production":
        Base.metadata.create_all(bind=engine)
    yield


def _parse_rate_limit(value: str) -> tuple[int, int]:
    count, _, unit = value.partition("/")
    seconds = {"second": 1, "minute": 60, "hour": 3600}.get(unit.strip(), 60)
    return int(count), seconds


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description=(
            "Backend platform for managing telecom customers, plans, SIMs, devices, subscriptions, "
            "usage, network infrastructure, outages, support tickets, SLAs and operational analytics."
        ),
        lifespan=lifespan,
    )

    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    max_requests, window = _parse_rate_limit(settings.RATE_LIMIT_DEFAULT)
    app.add_middleware(RateLimitMiddleware, max_requests=max_requests, window_seconds=window)
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)



app = create_app()
