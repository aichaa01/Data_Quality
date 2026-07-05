"""
Router Anomalies — enregistrements EN ATTENTE de decision
Regles actives (dimensions sans accents) :
  TX_GAB_SANS_ID, TX_NON_GAB_AVEC_ID, CARTE_ACTIVE_COMPTE_CLOTURE,
  TX_COMPTE_INEXISTANT, CLIENT_AGENCE_FERMEE, COMPTE_CLIENT_INEXISTANT,
  DIGITAL_CLIENT_INEXISTANT, CONTACT_INVALIDE
"""

from fastapi import APIRouter, Query
from app.services.db import query, scalar

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


def _excl(rule_id: str, id_expr: str) -> str:
    """Sous-requete excluant les enregistrements deja decides (directs ou cascade)."""
    return f"""
        NOT EXISTS (
            SELECT 1 FROM admin_decisions ad
            WHERE ad.rule_id = '{rule_id}' AND ad.record_id = {id_expr}
        )
    """


RULES = {
    "TX_GAB_SANS_ID": {
        "description": "Transaction GAB sans identifiant de guichet",
        "dimension":   "coherence",
        "table":       "transactions",
        "id_col":      "transaction_id",
        "select":      "transaction_id, compte_id, date_transaction, montant, canal, gab_id",
        "from":        "transactions",
        "where":       "canal = 'GAB' AND gab_id IS NULL",
    },
    "TX_NON_GAB_AVEC_ID": {
        "description": "Transaction non-GAB avec identifiant de guichet",
        "dimension":   "coherence",
        "table":       "transactions",
        "id_col":      "transaction_id",
        "select":      "transaction_id, compte_id, date_transaction, montant, canal, gab_id",
        "from":        "transactions",
        "where":       "canal != 'GAB' AND gab_id IS NOT NULL",
    },
    "CARTE_ACTIVE_COMPTE_CLOTURE": {
        "description": "Carte active associee a un compte cloture",
        "dimension":   "coherence",
        "table":       "cartes",
        "id_col":      "c.carte_id",
        "select":      "c.carte_id, c.compte_id, c.type_carte, c.statut AS statut_carte, co.statut AS statut_compte",
        "from":        "cartes c JOIN comptes co ON c.compte_id = co.compte_id",
        "where":       "c.statut = 'active' AND co.statut = 'cloture'",
    },
    "TX_COMPTE_INEXISTANT": {
        "description": "Transaction referencant un compte absent",
        "dimension":   "coherence",
        "table":       "transactions",
        "id_col":      "t.transaction_id",
        "select":      "t.transaction_id, t.compte_id, t.date_transaction, t.montant, t.canal",
        "from":        "transactions t",
        "where":       "NOT EXISTS (SELECT 1 FROM comptes c WHERE c.compte_id = t.compte_id)",
    },
    "CLIENT_AGENCE_FERMEE": {
        "description": "Client rattache a une agence fermee",
        "dimension":   "coherence",
        "table":       "clients",
        "id_col":      "cl.client_id",
        "select":      "cl.client_id, cl.nom, cl.prenom, cl.agence_id, a.statut AS statut_agence",
        "from":        "clients cl JOIN agences a ON cl.agence_id = a.agence_id",
        "where":       "a.statut = 'fermee'",
    },
    "COMPTE_CLIENT_INEXISTANT": {
        "description": "Compte referencant un client absent",
        "dimension":   "coherence",
        "table":       "comptes",
        "id_col":      "co.compte_id",
        "select":      "co.compte_id, co.client_id, co.type_compte, co.statut",
        "from":        "comptes co",
        "where":       "NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = co.client_id)",
    },
    "DIGITAL_CLIENT_INEXISTANT": {
        "description": "Usage digital referencant un client absent",
        "dimension":   "coherence",
        "table":       "digital_usage",
        "id_col":      "du.usage_id",
        "select":      "du.usage_id, du.client_id, du.canal, du.action, du.date_connexion",
        "from":        "digital_usage du",
        "where":       "NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = du.client_id)",
    },
    "CONTACT_INVALIDE": {
        "description": "Client sans aucun moyen de contact valide (email invalide ET telephone NULL)",
        "dimension":   "exactitude",
        "table":       "clients",
        "id_col":      "client_id",
        "select":      "client_id, nom, prenom, email, telephone",
        "from":        "clients",
        "where":       "telephone IS NULL AND (email IS NULL OR email NOT LIKE '%@%' OR email NOT LIKE '%.%')",
    },
}


def _count_pending(rule_id: str, rule: dict) -> int:
    try:
        excl = _excl(rule_id, rule["id_col"])
        sql  = f"SELECT COUNT(*) FROM {rule['from']} WHERE {rule['where']} AND {excl}"
        return scalar(sql) or 0
    except Exception as e:
        print(f"[ANOMALIES] count_pending {rule_id}: {e}")
        return 0


def _sample_pending(rule_id: str, rule: dict, limit: int, offset: int) -> list:
    try:
        excl = _excl(rule_id, rule["id_col"])
        sql  = f"""
            SELECT {rule['select']}
            FROM {rule['from']}
            WHERE {rule['where']} AND {excl}
            LIMIT :limit OFFSET :offset
        """
        return query(sql, {"limit": limit, "offset": offset})
    except Exception as e:
        print(f"[ANOMALIES] sample_pending {rule_id}: {e}")
        return []


@router.get("/summary")
def get_summary():
    result = []
    for rule_id, rule in RULES.items():
        try:
            total_table = scalar(f"SELECT COUNT(*) FROM {rule['table']}") or 1
        except Exception:
            total_table = 1
        en_attente = _count_pending(rule_id, rule)
        result.append({
            "rule_id":       rule_id,
            "description":   rule["description"],
            "dimension":     rule["dimension"],
            "anomaly_count": en_attente,
            "anomaly_pct":   round(en_attente / total_table * 100, 2),
        })
    return result


@router.get("/{rule_id}")
def get_rule_detail(
    rule_id: str,
    limit:   int = Query(default=20, ge=1, le=100),
    offset:  int = Query(default=0,  ge=0),
):
    rule = RULES.get(rule_id)
    if not rule:
        return {"error": "Regle inconnue"}

    total = _count_pending(rule_id, rule)
    data  = _sample_pending(rule_id, rule, limit, offset)

    # Enregistrements rejetes en cascade pour cette regle (affiches avec badge)
    try:
        cascade = query("""
            SELECT ad.record_id, ad.decided_at, ad.comment
            FROM admin_decisions ad
            WHERE ad.rule_id = :rule_id AND ad.cascade_from IS NOT NULL
            ORDER BY ad.decided_at DESC
            LIMIT 50
        """, {"rule_id": rule_id})
    except Exception:
        cascade = []

    return {
        "rule_id":   rule_id,
        "dimension": rule["dimension"],
        "page":      {"total": total, "limit": limit, "offset": offset},
        "data":      data,
        "cascade_rejected": cascade,
    }