"""
Service de connexion PostgreSQL
Al Barid Bank — Data Quality Platform
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "barid_bank")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin123")


def get_engine():
    url = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    return create_engine(url, poolclass=QueuePool, pool_size=5, max_overflow=10)


engine = get_engine()


def query(sql: str, params: dict = None) -> list[dict]:
    """Execute une requete SELECT ou DML avec commit automatique."""
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            try:
                cols = result.keys()
                return [dict(zip(cols, row)) for row in result.fetchall()]
            except Exception:
                return []
    except Exception as e:
        print(f"[DB ERROR] query() failed: {e}\nSQL: {sql}\nParams: {params}")
        raise


def scalar(sql: str, params: dict = None):
    """Execute une requete et retourne une seule valeur."""
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.scalar()
    except Exception as e:
        print(f"[DB ERROR] scalar() failed: {e}\nSQL: {sql}\nParams: {params}")
        raise