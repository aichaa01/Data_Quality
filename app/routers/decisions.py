"""
Router Decisions — avec logique de cascade
Quand un parent est rejete, ses descendants sont automatiquement rejetes.
Cascade : client -> comptes -> transactions, cartes, digital_usage
           compte -> transactions, cartes
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.db import query, scalar

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


class DecisionIn(BaseModel):
    rule_id:    str
    table_name: str
    record_id:  int
    decision:   str
    severity:   str
    comment:    Optional[str] = None


class BulkDecisionIn(BaseModel):
    rule_id:  str
    decision: str
    severity: str
    comment:  Optional[str] = None


RULE_TABLE_MAP = {
    "TX_GAB_SANS_ID":              "transactions",
    "TX_NON_GAB_AVEC_ID":          "transactions",
    "TX_COMPTE_INEXISTANT":        "transactions",
    "CARTE_ACTIVE_COMPTE_CLOTURE": "cartes",
    "CLIENT_AGENCE_FERMEE":        "clients",
    "COMPTE_CLIENT_INEXISTANT":    "comptes",
    "DIGITAL_CLIENT_INEXISTANT":   "digital_usage",
    "CONTACT_INVALIDE":            "clients",
}

# Decisions automatiques par regle
RULE_AUTO = {
    "TX_GAB_SANS_ID":              ("accepted", "low",    "Transaction GAB acceptee malgre l'absence de gab_id"),
    "TX_NON_GAB_AVEC_ID":          ("accepted", "medium", "Transaction non-GAB acceptee malgre la presence d'un gab_id"),
    "CARTE_ACTIVE_COMPTE_CLOTURE": ("rejected", "high",   "Carte active sur compte cloture — rejetee"),
    "TX_COMPTE_INEXISTANT":        ("rejected", "high",   "Transaction sur compte inexistant — rejetee"),
    "CLIENT_AGENCE_FERMEE":        ("accepted", "medium", "Client accepte — agence fermee, transfert vers agence active recommande"),
    "COMPTE_CLIENT_INEXISTANT":    ("rejected", "high",   "Compte sans client existant — rejete"),
    "DIGITAL_CLIENT_INEXISTANT":   ("rejected", "high",   "Usage digital sans client existant — rejete"),
    "CONTACT_INVALIDE":            ("rejected", "medium", "Client sans moyen de contact valide — rejete"),
}


def _insert_decision(rule_id, table_name, record_id, decision, severity, comment, cascade_from=None):
    """Insert une decision dans admin_decisions."""
    query("""
        INSERT INTO admin_decisions
            (rule_id, table_name, record_id, decision, severity, comment, cascade_from)
        VALUES
            (:rule_id, :table_name, :record_id, :decision, :severity, :comment, :cascade_from)
    """, {
        "rule_id":      rule_id,
        "table_name":   table_name,
        "record_id":    record_id,
        "decision":     decision,
        "severity":     severity,
        "comment":      comment or "",
        "cascade_from": cascade_from,
    })

    if decision == "rejected":
        try:
            query("""
                INSERT INTO rejected_records (rule_id, table_name, record_id, record_data)
                VALUES (:rule_id, :table_name, :record_id, :data::jsonb)
            """, {
                "rule_id":    rule_id,
                "table_name": table_name,
                "record_id":  record_id,
                "data":       f'{{"record_id":{record_id},"rule_id":"{rule_id}"}}',
            })
        except Exception as e:
            print(f"[DECISIONS] rejected_records warning: {e}")


def _cascade_reject(parent_rule_id: str, parent_table: str, parent_id: int, parent_decision_id: int):
    """
    Rejette en cascade les descendants d'un enregistrement parent rejete.
    client  -> comptes  -> transactions, cartes
            -> digital_usage
    compte  -> transactions, cartes
    """
    comment = f"Rejete en cascade depuis {parent_table} #{parent_id} (regle {parent_rule_id})"

    if parent_table == "clients":
        # Comptes du client
        comptes = query("SELECT compte_id FROM comptes WHERE client_id = :id", {"id": parent_id})
        for co in comptes:
            cid = co["compte_id"]
            _insert_decision("COMPTE_CLIENT_INEXISTANT", "comptes", cid, "rejected", "high", comment, parent_decision_id)
            # Transactions du compte
            txs = query("SELECT transaction_id FROM transactions WHERE compte_id = :id", {"id": cid})
            for tx in txs:
                _insert_decision("TX_COMPTE_INEXISTANT", "transactions", tx["transaction_id"], "rejected", "high", comment, parent_decision_id)
            # Cartes du compte
            cartes = query("SELECT carte_id FROM cartes WHERE compte_id = :id", {"id": cid})
            for ca in cartes:
                _insert_decision("CARTE_ACTIVE_COMPTE_CLOTURE", "cartes", ca["carte_id"], "rejected", "high", comment, parent_decision_id)
        # Digital usage du client
        usages = query("SELECT usage_id FROM digital_usage WHERE client_id = :id", {"id": parent_id})
        for us in usages:
            _insert_decision("DIGITAL_CLIENT_INEXISTANT", "digital_usage", us["usage_id"], "rejected", "high", comment, parent_decision_id)

    elif parent_table == "comptes":
        # Transactions du compte
        txs = query("SELECT transaction_id FROM transactions WHERE compte_id = :id", {"id": parent_id})
        for tx in txs:
            _insert_decision("TX_COMPTE_INEXISTANT", "transactions", tx["transaction_id"], "rejected", "high", comment, parent_decision_id)
        # Cartes du compte
        cartes = query("SELECT carte_id FROM cartes WHERE compte_id = :id", {"id": parent_id})
        for ca in cartes:
            _insert_decision("CARTE_ACTIVE_COMPTE_CLOTURE", "cartes", ca["carte_id"], "rejected", "high", comment, parent_decision_id)


@router.post("/")
def create_decision(body: DecisionIn):
    if body.decision not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Decision invalide")
    if body.severity not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="Severite invalide")
    if body.rule_id not in RULE_TABLE_MAP:
        raise HTTPException(status_code=400, detail=f"Regle inconnue: {body.rule_id}")

    table_name = RULE_TABLE_MAP[body.rule_id]

    try:
        _insert_decision(body.rule_id, table_name, body.record_id,
                         body.decision, body.severity, body.comment)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Cascade si rejet
    if body.decision == "rejected" and table_name in ("clients", "comptes"):
        try:
            dec_id = scalar("SELECT MAX(id) FROM admin_decisions WHERE rule_id=:r AND record_id=:i",
                            {"r": body.rule_id, "i": body.record_id})
            _cascade_reject(body.rule_id, table_name, body.record_id, dec_id)
        except Exception as e:
            print(f"[CASCADE] warning: {e}")

    # Suivi du modele : completer la ou les predictions faites sur cet
    # enregistrement avec la decision finale du reporter, et indiquer si la
    # suggestion du modele etait correcte.
    try:
        query("""
            UPDATE model_predictions
            SET decision_reporter   = :decision,
                prediction_correcte = (prediction_modele = :decision),
                decided_at          = NOW()
            WHERE rule_id = :rule_id
              AND record_id = :record_id
              AND decision_reporter IS NULL
        """, {
            "decision":  body.decision,
            "rule_id":   body.rule_id,
            "record_id": body.record_id,
        })
    except Exception as e:
        print(f"[PREDICTION] Suivi non mis a jour : {e}")

    return {"status": "ok", "decision": body.decision}


@router.post("/bulk")
def bulk_decision(body: BulkDecisionIn):
    if body.rule_id not in RULE_TABLE_MAP:
        raise HTTPException(status_code=400, detail="Regle inconnue")
    auto = RULE_AUTO.get(body.rule_id)
    if not auto:
        raise HTTPException(status_code=400, detail="Regle sans decision auto")

    decision, severity, comment = auto
    table_name = RULE_TABLE_MAP[body.rule_id]

    # Recuperer tous les enregistrements en attente
    from app.routers.anomalies import RULES, _sample_pending
    rule   = RULES.get(body.rule_id)
    if not rule:
        raise HTTPException(status_code=400, detail="Regle inconnue dans anomalies")

    records = _sample_pending(body.rule_id, rule, limit=10000, offset=0)
    count   = 0
    for rec in records:
        id_col  = rule["id_col"].split(".")[-1]
        rec_id  = rec.get(id_col) or rec.get(list(rec.keys())[0])
        try:
            _insert_decision(body.rule_id, table_name, rec_id, decision, severity, comment)
            if decision == "rejected" and table_name in ("clients", "comptes"):
                dec_id = scalar("SELECT MAX(id) FROM admin_decisions WHERE rule_id=:r AND record_id=:i",
                                {"r": body.rule_id, "i": rec_id})
                _cascade_reject(body.rule_id, table_name, rec_id, dec_id)
            count += 1
        except Exception as e:
            print(f"[BULK] skip {rec_id}: {e}")

    return {"status": "ok", "processed": count, "decision": decision}


@router.get("/stats")
def get_stats():
    try:
        total    = scalar("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NULL") or 0
        accepted = scalar("SELECT COUNT(*) FROM admin_decisions WHERE decision='accepted' AND cascade_from IS NULL") or 0
        rejected = scalar("SELECT COUNT(*) FROM admin_decisions WHERE decision='rejected' AND cascade_from IS NULL") or 0
        high     = scalar("SELECT COUNT(*) FROM admin_decisions WHERE severity='high' AND cascade_from IS NULL") or 0
        return {"total": total, "accepted": accepted, "rejected": rejected, "high_severity": high}
    except Exception:
        return {"total": 0, "accepted": 0, "rejected": 0, "high_severity": 0}


@router.get("/")
def list_decisions(
    limit:    int = Query(default=25, ge=1, le=100),
    offset:   int = Query(default=0,  ge=0),
    decision: Optional[str] = None,
    rule_id:  Optional[str] = None,
    severity: Optional[str] = None,
):
    where  = ["cascade_from IS NULL"]   # n'afficher que les decisions directes
    params = {"limit": limit, "offset": offset}
    if decision: where.append("decision=:decision"); params["decision"] = decision
    if rule_id:  where.append("rule_id=:rule_id");   params["rule_id"]  = rule_id
    if severity: where.append("severity=:severity"); params["severity"] = severity
    wc = " AND ".join(where)
    try:
        total = scalar(f"SELECT COUNT(*) FROM admin_decisions WHERE {wc}", params) or 0
        data  = query(f"""
            SELECT id, rule_id, table_name, record_id, decision, severity, comment, decided_at
            FROM admin_decisions WHERE {wc}
            ORDER BY decided_at DESC LIMIT :limit OFFSET :offset
        """, params)
        return {"total": total, "data": data}
    except Exception as e:
        print(f"[DECISIONS] list error: {e}")
        return {"total": 0, "data": []}
