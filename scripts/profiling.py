"""
Phase 3 — Data Profiling
Al Barid Bank — Data Quality Platform
Profiling generique + regles metier cross-tables

Aligne sur les 8 regles actives dans app/routers/anomalies.py
Dimensions sans accents : coherence, unicite, exactitude, fraicheur
"""

import os
import json
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "barid_bank")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin123")

FRESHNESS_THRESHOLD_YEARS = 5  # Donnees de plus de 5 ans = obsoletes

OUTPUT_DIR = "data/processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_engine():
    url = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    return create_engine(url)


# ─────────────────────────────────────────────
# NIVEAU 1 — PROFILING GENERIQUE
# ─────────────────────────────────────────────

TABLES_CONFIG = {
    "agences": {
        "numeric_cols":  [],
        "date_cols":     ["date_ouverture", "date_fermeture"],
        "text_cols":     ["nom_agence", "ville"],
        "unique_cols":   ["agence_id"],
    },
    "clients": {
        "numeric_cols":  [],
        "date_cols":     ["date_naissance", "date_creation"],
        "text_cols":     ["cin", "email", "telephone"],
        "unique_cols":   ["client_id", "cin"],
    },
    "comptes": {
        "numeric_cols":  ["solde"],
        "date_cols":     ["date_ouverture"],
        "text_cols":     [],
        "unique_cols":   ["compte_id"],
    },
    "cartes": {
        "numeric_cols":  [],
        "date_cols":     ["date_expiration"],
        "text_cols":     [],
        "unique_cols":   ["carte_id"],
    },
    "gabs": {
        "numeric_cols":  [],
        "date_cols":     [],
        "text_cols":     [],
        "unique_cols":   ["gab_id"],
    },
    "transactions": {
        "numeric_cols":  ["montant"],
        "date_cols":     ["date_transaction"],
        "text_cols":     [],
        "unique_cols":   ["transaction_id"],
    },
    "digital_usage": {
        "numeric_cols":  [],
        "date_cols":     ["date_connexion"],
        "text_cols":     [],
        "unique_cols":   ["usage_id"],
    },
}


def profile_generic(engine):
    print("\nProfiling generique")
    results = {}

    for table, config in TABLES_CONFIG.items():
        print(f"  -> {table}")
        df = pd.read_sql(f"SELECT * FROM {table}", engine)
        total = len(df)
        table_profile = {"total_rows": total, "columns": {}, "duplicates": {}}

        # Completude par colonne
        for col in df.columns:
            null_count = int(df[col].isna().sum())
            table_profile["columns"][col] = {
                "null_count":       null_count,
                "completeness_pct": round((1 - null_count / total) * 100, 2) if total > 0 else 0,
                "distinct_count":   int(df[col].nunique()),
            }

        # Stats numeriques
        for col in config["numeric_cols"]:
            if col in df.columns:
                table_profile["columns"][col].update({
                    "min":    round(float(df[col].min()), 2),
                    "max":    round(float(df[col].max()), 2),
                    "mean":   round(float(df[col].mean()), 2),
                    "median": round(float(df[col].median()), 2),
                    "std":    round(float(df[col].std()), 2),
                })

        # Fraicheur des dates
        now = pd.Timestamp.now()
        threshold = now - pd.DateOffset(years=FRESHNESS_THRESHOLD_YEARS)
        for col in config["date_cols"]:
            if col in df.columns:
                col_dates = pd.to_datetime(df[col], errors="coerce")
                stale_count = int((col_dates < threshold).sum())
                table_profile["columns"][col].update({
                    "min_date":    str(col_dates.min()) if not pd.isna(col_dates.min()) else None,
                    "max_date":    str(col_dates.max()) if not pd.isna(col_dates.max()) else None,
                    "stale_count": stale_count,
                    "stale_pct":   round(stale_count / total * 100, 2) if total > 0 else 0,
                })

        # Unicite
        for col in config["unique_cols"]:
            if col in df.columns:
                dup_count = int(df[col].duplicated().sum())
                table_profile["duplicates"][col] = {
                    "duplicate_count": dup_count,
                    "duplicate_pct":   round(dup_count / total * 100, 2) if total > 0 else 0,
                }

        results[table] = table_profile

    return results


# ─────────────────────────────────────────────
# NIVEAU 2 — PROFILING METIER (REGLES CROSS-TABLES)
# Aligne exactement sur les 8 regles de app/routers/anomalies.py
# Valeurs de statut sans accents : cloture, fermee
# ─────────────────────────────────────────────

BUSINESS_RULES = {

    "TX_GAB_SANS_ID": {
        "description": "Transaction canal=GAB mais gab_id est NULL",
        "dimension":   "coherence",
        "tables":      ["transactions"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM transactions
            WHERE canal = 'GAB' AND gab_id IS NULL
        """,
        "sample_sql": """
            SELECT transaction_id, compte_id, date_transaction, canal, gab_id
            FROM transactions
            WHERE canal = 'GAB' AND gab_id IS NULL
            LIMIT 5
        """
    },

    "TX_NON_GAB_AVEC_ID": {
        "description": "Transaction canal!=GAB mais gab_id est renseigne",
        "dimension":   "coherence",
        "tables":      ["transactions"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM transactions
            WHERE canal != 'GAB' AND gab_id IS NOT NULL
        """,
        "sample_sql": """
            SELECT transaction_id, compte_id, date_transaction, canal, gab_id
            FROM transactions
            WHERE canal != 'GAB' AND gab_id IS NOT NULL
            LIMIT 5
        """
    },

    "CARTE_ACTIVE_COMPTE_CLOTURE": {
        "description": "Carte active liee a un compte cloture",
        "dimension":   "coherence",
        "tables":      ["cartes", "comptes"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM cartes c
            JOIN comptes co ON c.compte_id = co.compte_id
            WHERE c.statut = 'active' AND co.statut = 'cloture'
        """,
        "sample_sql": """
            SELECT c.carte_id, c.compte_id, c.statut AS statut_carte,
                   co.statut AS statut_compte
            FROM cartes c
            JOIN comptes co ON c.compte_id = co.compte_id
            WHERE c.statut = 'active' AND co.statut = 'cloture'
            LIMIT 5
        """
    },

    "TX_COMPTE_INEXISTANT": {
        "description": "Transaction avec compte_id inexistant dans la table comptes",
        "dimension":   "coherence",
        "tables":      ["transactions", "comptes"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM transactions t
            WHERE NOT EXISTS (
                SELECT 1 FROM comptes c WHERE c.compte_id = t.compte_id
            )
        """,
        "sample_sql": """
            SELECT t.transaction_id, t.compte_id, t.date_transaction, t.montant
            FROM transactions t
            WHERE NOT EXISTS (
                SELECT 1 FROM comptes c WHERE c.compte_id = t.compte_id
            )
            LIMIT 5
        """
    },

    "CLIENT_AGENCE_FERMEE": {
        "description": "Client rattache a une agence fermee",
        "dimension":   "coherence",
        "tables":      ["clients", "agences"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM clients cl
            JOIN agences a ON cl.agence_id = a.agence_id
            WHERE a.statut = 'fermee'
        """,
        "sample_sql": """
            SELECT cl.client_id, cl.nom, cl.prenom, cl.agence_id,
                   a.nom_agence, a.statut, a.date_fermeture
            FROM clients cl
            JOIN agences a ON cl.agence_id = a.agence_id
            WHERE a.statut = 'fermee'
            LIMIT 5
        """
    },

    "COMPTE_CLIENT_INEXISTANT": {
        "description": "Compte avec client_id qui n'existe pas dans clients",
        "dimension":   "coherence",
        "tables":      ["comptes", "clients"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM comptes co
            WHERE NOT EXISTS (
                SELECT 1 FROM clients cl WHERE cl.client_id = co.client_id
            )
        """,
        "sample_sql": """
            SELECT co.compte_id, co.client_id, co.type_compte, co.statut
            FROM comptes co
            WHERE NOT EXISTS (
                SELECT 1 FROM clients cl WHERE cl.client_id = co.client_id
            )
            LIMIT 5
        """
    },

    "DIGITAL_CLIENT_INEXISTANT": {
        "description": "Usage digital avec client_id inexistant dans clients",
        "dimension":   "coherence",
        "tables":      ["digital_usage", "clients"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM digital_usage du
            WHERE NOT EXISTS (
                SELECT 1 FROM clients cl WHERE cl.client_id = du.client_id
            )
        """,
        "sample_sql": """
            SELECT du.usage_id, du.client_id, du.date_connexion, du.canal
            FROM digital_usage du
            WHERE NOT EXISTS (
                SELECT 1 FROM clients cl WHERE cl.client_id = du.client_id
            )
            LIMIT 5
        """
    },

    "CONTACT_INVALIDE": {
        "description": "Client sans aucun moyen de contact valide (email invalide ET telephone NULL)",
        "dimension":   "exactitude",
        "tables":      ["clients"],
        "sql": """
            SELECT COUNT(*) AS count
            FROM clients
            WHERE telephone IS NULL
              AND (email IS NULL OR email NOT LIKE '%@%' OR email NOT LIKE '%.%')
        """,
        "sample_sql": """
            SELECT client_id, nom, prenom, email, telephone
            FROM clients
            WHERE telephone IS NULL
              AND (email IS NULL OR email NOT LIKE '%@%' OR email NOT LIKE '%.%')
            LIMIT 5
        """
    },

}


def profile_business_rules(engine):
    print("\nProfiling metier (regles cross-tables)...")
    results = {}

    with engine.connect() as conn:
        for rule_id, rule in BUSINESS_RULES.items():
            print(f"  -> {rule_id}")
            try:
                count_result = conn.execute(text(rule["sql"]))
                count = count_result.scalar()

                ref_table = rule["tables"][0]
                total = conn.execute(text(f"SELECT COUNT(*) FROM {ref_table}")).scalar()

                sample_df = pd.read_sql(text(rule["sample_sql"]), conn)
                sample = sample_df.to_dict(orient="records")

                results[rule_id] = {
                    "description":  rule["description"],
                    "dimension":    rule["dimension"],
                    "tables":       rule["tables"],
                    "anomaly_count": int(count),
                    "total_ref":    int(total),
                    "anomaly_pct":  round(count / total * 100, 2) if total > 0 else 0,
                    "sample":       sample,
                    "status":       "anomalies detectees" if count > 0 else "ok",
                }

            except Exception as e:
                results[rule_id] = {"error": str(e)}
                print(f"Erreur : {e}")

    return results


# ─────────────────────────────────────────────
# RAPPORT FINAL
# ─────────────────────────────────────────────

def print_business_summary(business_results):
    print("\n" + "=" * 60)
    print("  RESUME — REGLES METIER")
    print("=" * 60)
    print(f"  {'Regle':<35} {'Anomalies':>10} {'%':>8}  Statut")
    print(f"  {'-'*35} {'-'*10} {'-'*8}  {'-'*20}")
    for rule_id, result in business_results.items():
        if "error" not in result:
            print(
                f"  {rule_id:<35} {result['anomaly_count']:>10,} "
                f"{result['anomaly_pct']:>7.2f}%  {result['status']}"
            )
    print("=" * 60)


def save_reports(generic_results, business_results):
    report = {
        "generated_at": datetime.now().isoformat(),
        "generic_profiling":  generic_results,
        "business_rules":     business_results,
    }

    json_path = f"{OUTPUT_DIR}/profiling_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nRapport JSON sauvegarde -> {json_path}")

    rows = []
    for rule_id, result in business_results.items():
        if "error" not in result:
            rows.append({
                "rule_id":       rule_id,
                "description":   result["description"],
                "dimension":     result["dimension"],
                "tables":        ", ".join(result["tables"]),
                "anomaly_count": result["anomaly_count"],
                "total_ref":     result["total_ref"],
                "anomaly_pct":   result["anomaly_pct"],
                "status":        result["status"],
            })

    csv_path = f"{OUTPUT_DIR}/profiling_summary.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(f"Resume CSV sauvegarde -> {csv_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Data Profiling")
    print("=" * 60)

    engine = get_engine()

    generic_results  = profile_generic(engine)
    business_results = profile_business_rules(engine)

    print_business_summary(business_results)
    save_reports(generic_results, business_results)

    print("\nPhase 3 terminee avec succes.")