"""
Phase Labelisation automatique
Al Barid Bank — Data Quality Platform
Remplit admin_decisions selon les regles metier, AVEC cascade.
Idempotent. Option B : les valides ne sont pas labelises ici.
"""

import os
from sqlalchemy import create_engine, text

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "barid_bank")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin123")


def get_engine():
    url = (f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
           f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    return create_engine(url)


RULES = {
    "CONTACT_INVALIDE": {
        "table": "clients", "id_col": "client_id",
        "decision": "rejected", "severity": "medium",
        "comment": "Client sans moyen de contact valide — rejete",
        "detect": """
            SELECT client_id AS rid FROM clients
            WHERE telephone IS NULL
              AND (email IS NULL OR email NOT LIKE '%@%' OR email NOT LIKE '%.%')
        """,
    },
    "CLIENT_AGENCE_FERMEE": {
        "table": "clients", "id_col": "client_id",
        "decision": "accepted", "severity": "medium",
        "comment": "Client accepte — transfert vers une agence active recommande",
        "detect": """
            SELECT cl.client_id AS rid
            FROM clients cl JOIN agences a ON cl.agence_id = a.agence_id
            WHERE a.statut = 'fermee'
        """,
    },
    "COMPTE_CLIENT_INEXISTANT": {
        "table": "comptes", "id_col": "compte_id",
        "decision": "rejected", "severity": "high",
        "comment": "Compte sans client existant — rejete",
        "detect": """
            SELECT co.compte_id AS rid FROM comptes co
            WHERE NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = co.client_id)
        """,
    },
    "CARTE_ACTIVE_COMPTE_CLOTURE": {
        "table": "cartes", "id_col": "carte_id",
        "decision": "rejected", "severity": "high",
        "comment": "Carte active sur compte cloture — rejetee",
        "detect": """
            SELECT c.carte_id AS rid
            FROM cartes c JOIN comptes co ON c.compte_id = co.compte_id
            WHERE c.statut = 'active' AND co.statut = 'cloture'
        """,
    },
    "TX_COMPTE_INEXISTANT": {
        "table": "transactions", "id_col": "transaction_id",
        "decision": "rejected", "severity": "high",
        "comment": "Transaction sur compte inexistant — rejetee",
        "detect": """
            SELECT t.transaction_id AS rid FROM transactions t
            WHERE NOT EXISTS (SELECT 1 FROM comptes c WHERE c.compte_id = t.compte_id)
        """,
    },
    "TX_GAB_SANS_ID": {
        "table": "transactions", "id_col": "transaction_id",
        "decision": "accepted", "severity": "low",
        "comment": "Transaction GAB acceptee malgre l'absence de gab_id",
        "detect": """
            SELECT transaction_id AS rid FROM transactions
            WHERE canal = 'GAB' AND gab_id IS NULL
        """,
    },
    "TX_NON_GAB_AVEC_ID": {
        "table": "transactions", "id_col": "transaction_id",
        "decision": "accepted", "severity": "medium",
        "comment": "Transaction non-GAB acceptee malgre la presence d'un gab_id",
        "detect": """
            SELECT transaction_id AS rid FROM transactions
            WHERE canal != 'GAB' AND gab_id IS NOT NULL
        """,
    },
    "DIGITAL_CLIENT_INEXISTANT": {
        "table": "digital_usage", "id_col": "usage_id",
        "decision": "rejected", "severity": "high",
        "comment": "Usage digital sans client existant — rejete",
        "detect": """
            SELECT du.usage_id AS rid FROM digital_usage du
            WHERE NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = du.client_id)
        """,
    },
}

ORDER = [
    "CONTACT_INVALIDE", "CLIENT_AGENCE_FERMEE", "COMPTE_CLIENT_INEXISTANT",
    "CARTE_ACTIVE_COMPTE_CLOTURE", "TX_COMPTE_INEXISTANT",
    "TX_GAB_SANS_ID", "TX_NON_GAB_AVEC_ID", "DIGITAL_CLIENT_INEXISTANT",
]


def already_decided(conn, rule_id, rid):
    r = conn.execute(text(
        "SELECT 1 FROM admin_decisions WHERE rule_id = :r AND record_id = :i LIMIT 1"),
        {"r": rule_id, "i": rid}).fetchone()
    return r is not None


def insert_decision(conn, rule_id, table, rid, decision, severity, comment, cascade_from=None):
    conn.execute(text("""
        INSERT INTO admin_decisions
            (rule_id, table_name, record_id, decision, severity, comment, cascade_from)
        VALUES (:rule_id, :table, :rid, :decision, :severity, :comment, :cascade_from)
    """), {"rule_id": rule_id, "table": table, "rid": rid,
           "decision": decision, "severity": severity,
           "comment": comment, "cascade_from": cascade_from})

    if decision == "rejected":
        conn.execute(text("""
            INSERT INTO rejected_records (rule_id, table_name, record_id, record_data)
            VALUES (:rule_id, :table, :rid, CAST(:data AS jsonb))
        """), {"rule_id": rule_id, "table": table, "rid": rid,
               "data": f'{{"record_id":{rid},"rule_id":"{rule_id}"}}'})


def get_last_decision_id(conn, rule_id, rid):
    return conn.execute(text("""
        SELECT MAX(id) FROM admin_decisions
        WHERE rule_id = :r AND record_id = :i AND cascade_from IS NULL
    """), {"r": rule_id, "i": rid}).scalar()


def cascade_reject(conn, parent_rule, parent_table, parent_id, parent_decision_id):
    comment = f"Rejete en cascade depuis {parent_table} #{parent_id} (regle {parent_rule})"

    if parent_table == "clients":
        for (cid,) in conn.execute(text(
            "SELECT compte_id FROM comptes WHERE client_id = :id"), {"id": parent_id}).fetchall():
            if not already_decided(conn, "COMPTE_CLIENT_INEXISTANT", cid):
                insert_decision(conn, "COMPTE_CLIENT_INEXISTANT", "comptes", cid,
                                "rejected", "high", comment, parent_decision_id)
            for (tx,) in conn.execute(text(
                "SELECT transaction_id FROM transactions WHERE compte_id = :id"), {"id": cid}).fetchall():
                if not already_decided(conn, "TX_COMPTE_INEXISTANT", tx):
                    insert_decision(conn, "TX_COMPTE_INEXISTANT", "transactions", tx,
                                    "rejected", "high", comment, parent_decision_id)
            for (ca,) in conn.execute(text(
                "SELECT carte_id FROM cartes WHERE compte_id = :id"), {"id": cid}).fetchall():
                if not already_decided(conn, "CARTE_ACTIVE_COMPTE_CLOTURE", ca):
                    insert_decision(conn, "CARTE_ACTIVE_COMPTE_CLOTURE", "cartes", ca,
                                    "rejected", "high", comment, parent_decision_id)
        for (us,) in conn.execute(text(
            "SELECT usage_id FROM digital_usage WHERE client_id = :id"), {"id": parent_id}).fetchall():
            if not already_decided(conn, "DIGITAL_CLIENT_INEXISTANT", us):
                insert_decision(conn, "DIGITAL_CLIENT_INEXISTANT", "digital_usage", us,
                                "rejected", "high", comment, parent_decision_id)

    elif parent_table == "comptes":
        for (tx,) in conn.execute(text(
            "SELECT transaction_id FROM transactions WHERE compte_id = :id"), {"id": parent_id}).fetchall():
            if not already_decided(conn, "TX_COMPTE_INEXISTANT", tx):
                insert_decision(conn, "TX_COMPTE_INEXISTANT", "transactions", tx,
                                "rejected", "high", comment, parent_decision_id)
        for (ca,) in conn.execute(text(
            "SELECT carte_id FROM cartes WHERE compte_id = :id"), {"id": parent_id}).fetchall():
            if not already_decided(conn, "CARTE_ACTIVE_COMPTE_CLOTURE", ca):
                insert_decision(conn, "CARTE_ACTIVE_COMPTE_CLOTURE", "cartes", ca,
                                "rejected", "high", comment, parent_decision_id)


def main():
    print("Labelisation automatique — Al Barid Bank")
    print("=" * 60)
    engine = get_engine()

    with engine.begin() as conn:
        for rule_id in ORDER:
            rule = RULES[rule_id]
            rows = conn.execute(text(rule["detect"])).fetchall()
            direct = 0
            cascaded = 0
            for (rid,) in rows:
                if already_decided(conn, rule_id, rid):
                    continue
                insert_decision(conn, rule_id, rule["table"], rid,
                                rule["decision"], rule["severity"], rule["comment"])
                direct += 1
                if rule["decision"] == "rejected" and rule["table"] in ("clients", "comptes"):
                    dec_id = get_last_decision_id(conn, rule_id, rid)
                    before = conn.execute(text(
                        "SELECT COUNT(*) FROM admin_decisions WHERE cascade_from = :d"),
                        {"d": dec_id}).scalar() or 0
                    cascade_reject(conn, rule_id, rule["table"], rid, dec_id)
                    after = conn.execute(text(
                        "SELECT COUNT(*) FROM admin_decisions WHERE cascade_from = :d"),
                        {"d": dec_id}).scalar() or 0
                    cascaded += (after - before)
            print(f"  {rule_id:<30} {rule['decision']:>9} | "
                  f"directs: {direct:>5} | cascade: {cascaded:>5}")

    print("=" * 60)
    with engine.connect() as conn:
        total    = conn.execute(text("SELECT COUNT(*) FROM admin_decisions")).scalar()
        direct   = conn.execute(text("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NULL")).scalar()
        cascade  = conn.execute(text("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NOT NULL")).scalar()
        accepted = conn.execute(text("SELECT COUNT(*) FROM admin_decisions WHERE decision='accepted'")).scalar()
        rejected = conn.execute(text("SELECT COUNT(*) FROM admin_decisions WHERE decision='rejected'")).scalar()

    print(f"  Total decisions    : {total:>6}")
    print(f"    - directes       : {direct:>6}")
    print(f"    - cascade        : {cascade:>6}")
    print(f"    - acceptees      : {accepted:>6}")
    print(f"    - rejetees       : {rejected:>6}")
    print("\nLabelisation terminee.")


if __name__ == "__main__":
    main()