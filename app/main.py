"""
Al Barid Bank — Data Quality Platform
FastAPI Backend
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from app.routers import dashboard, anomalies, decisions, prediction
from app.services.db import query
from app.services import model as ml
from app.services import contexts

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
        """
        CREATE TABLE IF NOT EXISTS model_predictions (
            id                 SERIAL PRIMARY KEY,
            table_origine      VARCHAR(100) NOT NULL,
            record_id          INTEGER      NOT NULL,
            rule_id            VARCHAR(100) NOT NULL,
            contexte_reporting VARCHAR(100) NOT NULL,
            valeur_metier      NUMERIC(15,2),
            prediction_modele  VARCHAR(10)  NOT NULL CHECK (prediction_modele IN ('accepted', 'rejected')),
            proba_rejet        NUMERIC(6,4),
            contexte_connu     BOOLEAN      DEFAULT TRUE,
            decision_reporter  VARCHAR(10)  CHECK (decision_reporter IN ('accepted', 'rejected')),
            prediction_correcte BOOLEAN,
            predicted_at       TIMESTAMP    DEFAULT NOW(),
            decided_at         TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reporting_contexts (
            contexte     VARCHAR(100) PRIMARY KEY,
            description  TEXT,
            is_trained   BOOLEAN   DEFAULT FALSE,
            usage_count  INTEGER   DEFAULT 0,
            created_at   TIMESTAMP DEFAULT NOW(),
            last_used_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_training_runs (
            id              SERIAL PRIMARY KEY,
            trained_at      TIMESTAMP DEFAULT NOW(),
            motif           TEXT,
            n_lignes        INTEGER,
            f1              NUMERIC(6,4),
            precision_score NUMERIC(6,4),
            rappel          NUMERIC(6,4),
            deployed        BOOLEAN DEFAULT FALSE,
            success         BOOLEAN DEFAULT TRUE,
            note            TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_predictions_record  ON model_predictions (table_origine, record_id)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_rule    ON model_predictions (rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_ctx     ON model_predictions (contexte_reporting)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_date    ON model_predictions (predicted_at)",
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


@app.on_event("startup")
def load_ml_model():
    """Charge le modele de prediction au demarrage."""
    ml.load_model()
    # Amorce le referentiel avec les contextes d'entrainement du modele
    if ml.is_ready():
        contexts.initialiser(ml.contextes_connus())
        print("[STARTUP] Referentiel des contextes initialise.")

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
app.include_router(prediction.router)

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