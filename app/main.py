import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware

from . import api, web
from .config import settings
from .db import pool, request_stats


@asynccontextmanager
async def lifespan(app):
    pool.open(wait=True)
    yield
    pool.close()


app = FastAPI(title="Библиотека: выдача книг", lifespan=lifespan)


@app.middleware("http")
async def timing(request: Request, call_next):
    """Время ответа целиком и доля базы данных - заголовками ответа."""
    stats = {"queries": 0, "db_seconds": 0.0}
    token = request_stats.set(stats)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_stats.reset(token)
    response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    response.headers["X-DB-Time-ms"] = f"{stats['db_seconds'] * 1000:.2f}"
    response.headers["X-DB-Queries"] = str(stats["queries"])
    return response


app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="library_session")
app.include_router(api.router)
app.include_router(web.router)
