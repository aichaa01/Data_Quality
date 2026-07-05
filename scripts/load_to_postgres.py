"""
Phase 2 — Chargement des CSV dans PostgreSQL
Al Barid Bank — Data Quality Platform
"""

import os
import time
import pandas as pd
from sqlalchemy import create_engine, text

# Variables d'environnement (injectées par docker-compose)
POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "barid_bank")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin123")

DATA_DIR = "data"

TABLES = [
    ("agences",       "agences.csv"),
    ("clients",       "clients.csv"),
    ("comptes",       "comptes.csv"),
    ("cartes",        "cartes.csv"),
    ("gabs",          "gabs.csv"),
    ("transactions",  "transactions.csv"),
    ("digital_usage", "digital_usage.csv"),
]

DATE_COLS = {
    "agences":       ["date_ouverture", "date_fermeture"],
    "clients":       ["date_naissance", "date_creation"],
    "comptes":       ["date_ouverture"],
    "cartes":        ["date_expiration"],
    "gabs":          [],
    "transactions":  ["date_transaction"],
    "digital_usage": ["date_connexion"],
}

# Colonnes a forcer en string — sinon pandas les bascule en float64
# des qu'une valeur NULL apparait dans la colonne (ex: telephone manquant)
DTYPE_OVERRIDE = {
    "clients": {"telephone": "string", "cin": "string"},
}


def get_engine():
    url = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    return create_engine(url)


def wait_for_db(engine, retries=15, delay=3):
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Connexion à PostgreSQL établie.\n")
            return True
        except Exception as e:
            print(f"Tentative {attempt}/{retries} — {e}")
            time.sleep(delay)
    raise RuntimeError("Impossible de se connecter à PostgreSQL.")


def truncate_tables(engine):
    tables_reverse = [t for t, _ in reversed(TABLES)]
    with engine.connect() as conn:
        for table in tables_reverse:
            conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
        conn.commit()
    print("Tables vidées.\n")


def load_table(engine, table_name, csv_file):
    csv_path = os.path.join(DATA_DIR, csv_file)
    if not os.path.exists(csv_path):
        print(f"  Fichier introuvable : {csv_path} — ignoré.")
        return 0

    print(f"  {csv_file} → '{table_name}'...")
    df = pd.read_csv(
        csv_path,
        parse_dates=DATE_COLS.get(table_name, []),
        dtype=DTYPE_OVERRIDE.get(table_name, {}),
        low_memory=False,
    )
    df = df.where(pd.notna(df), None)
    df = df.replace("", None)

    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi"
    )
    print(f" {len(df):>7,} lignes insérées")
    return len(df)


def verify_counts(engine):
    print("\nVérification finale :")
    print(f"  {'Table':<20} {'Lignes':>10}")
    print(f"  {'─'*20} {'─'*10}")
    with engine.connect() as conn:
        for table, _ in TABLES:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table:<20} {count:>10,}")


if __name__ == "__main__":
    print("Chargement des données — Al Barid Bank\n")
    engine = get_engine()
    wait_for_db(engine)
    truncate_tables(engine)

    total = 0
    start = time.time()
    for table_name, csv_file in TABLES:
        total += load_table(engine, table_name, csv_file)

    verify_counts(engine)
    print(f"\nTerminé — {total:,} lignes en {time.time()-start:.1f}s")