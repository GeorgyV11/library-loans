"""Доступ к PostgreSQL через psycopg 3 и пул соединений.

Каждый запрос к базе проходит через Db.execute: там считается число запросов
и суммарное время в базе за HTTP-запрос (контекст requests_stats). Middleware в
main.py отдаёт эти числа заголовками X-DB-Queries и X-DB-Time-ms.
"""
import contextvars
import time

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

request_stats: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "request_stats", default=None
)

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=settings.db_pool_size,
    kwargs={"options": f"-c search_path={settings.db_schema}"},
    open=False,
)


class Db:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        stats = request_stats.get()
        started = time.perf_counter()
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
        if stats is not None:
            stats["queries"] += 1
            stats["db_seconds"] += time.perf_counter() - started
        return rows

    def one(self, sql, params=None):
        rows = self.execute(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql, params=None):
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None


def get_db():
    """Зависимость FastAPI: одно соединение и одна транзакция на HTTP-запрос."""
    with pool.connection() as conn:
        yield Db(conn)
