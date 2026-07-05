"""
Router Profiling — Metriques generiques par table
"""

from fastapi import APIRouter
from app.services.db import query, scalar

router = APIRouter(prefix="/api/profiling", tags=["profiling"])

TABLES = ["agences", "clients", "comptes", "cartes", "gabs", "transactions", "digital_usage"]


@router.get("/summary")
def get_profiling_summary():
    """Nombre de lignes par table — pour la vue d'ensemble."""
    results = []
    for table in TABLES:
        total = scalar(f"SELECT COUNT(*) FROM {table}") or 0
        results.append({
            "table_name": table,
            "row_count":  total,
        })
    return results


@router.get("/{table}")
def get_table_profile(table: str):
    """Profil detaille d'une table — completude, unicite, stats."""
    if table not in TABLES:
        return {"error": f"Table '{table}' introuvable"}

    total = scalar(f"SELECT COUNT(*) FROM {table}") or 1

    cols_info = query(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = '{table}'
        AND table_schema = 'public'
        ORDER BY ordinal_position
    """)

    columns = []
    for col in cols_info:
        col_name    = col["column_name"]
        null_count  = scalar(f"SELECT COUNT(*) FROM {table} WHERE {col_name} IS NULL") or 0
        distinct    = scalar(f"SELECT COUNT(DISTINCT {col_name}) FROM {table}") or 0
        completude  = round((1 - null_count / total) * 100, 1) if total else 0

        columns.append({
            "column_name":   col_name,
            "data_type":     col["data_type"],
            "null_count":    null_count,
            "distinct_count": distinct,
            "completude":    completude,
        })

    return {
        "table_name":  table,
        "row_count":   total,
        "columns":     columns,
    }