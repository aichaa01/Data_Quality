"""
Al Barid Bank — Data Quality Platform
FastAPI Backend
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from app.routers import dashboard, anomalies, decisions
from app.services.db import query

app = FastAPI(
    title="Al Barid Bank — Data Quality API",
    description="Plateforme de qualité des données bancaires",
    version="1.0.0"
)


@app.on_event("startup")
def create_governance_tables():
    """Cree les tables de gouvernance si elles n'existent pas."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS admin_decisions (
            id          SERIAL PRIMARY KEY,
            rule_id     VARCHAR(100)  NOT NULL,
            table_name  VARCHAR(100)  NOT NULL,
            record_id   INTEGER       NOT NULL,
            decision    VARCHAR(10)   NOT NULL CHECK (decision IN ('accepted', 'rejected')),
            severity    VARCHAR(10)   NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
            comment     TEXT,
            decided_at  TIMESTAMP     DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS rejected_records (
            id          SERIAL PRIMARY KEY,
            rule_id     VARCHAR(100)  NOT NULL,
            table_name  VARCHAR(100)  NOT NULL,
            record_id   INTEGER       NOT NULL,
            record_data JSONB         NOT NULL,
            decision_id INTEGER       REFERENCES admin_decisions(id),
            rejected_at TIMESTAMP     DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS validated_records (
            id              SERIAL PRIMARY KEY,
            table_name      VARCHAR(100) NOT NULL,
            record_id       INTEGER      NOT NULL,
            validated_at    TIMESTAMP    DEFAULT NOW(),
            pipeline_run_id VARCHAR(100)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_decisions_rule_id   ON admin_decisions (rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_decisions_decision   ON admin_decisions (decision)",
        "CREATE INDEX IF NOT EXISTS idx_decisions_decided_at ON admin_decisions (decided_at)",
        "CREATE INDEX IF NOT EXISTS idx_rejected_table       ON rejected_records (table_name)",
        "CREATE INDEX IF NOT EXISTS idx_rejected_rule        ON rejected_records (rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_validated_table      ON validated_records (table_name)",
    ]
    for ddl in ddl_statements:
        try:
            query(ddl)
        except Exception as e:
            print(f"[STARTUP] DDL warning: {e}")
    print("[STARTUP] Tables de gouvernance verifiees.")

# CORS pour le frontend JS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers API
app.include_router(dashboard.router)
app.include_router(anomalies.router)
app.include_router(decisions.router)

# Fichiers statiques (frontend)
app.mount("/static", StaticFiles(directory="app/frontend"), name="static")


# Pages HTML
NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

@app.get("/")
def index():
    return FileResponse("app/frontend/index.html", headers=NO_CACHE)

@app.get("/anomalies")
def anomalies_page():
    return FileResponse("app/frontend/anomalies.html", headers=NO_CACHE)


@app.get("/decisions")
def decisions_page():
    return FileResponse("app/frontend/decisions.html", headers=NO_CACHE)


@app.get("/health")
def health():
    return {"status": "ok", "service": "barid-bank-dq"}