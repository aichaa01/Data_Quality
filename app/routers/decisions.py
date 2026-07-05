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

RULE_AUTO = {
    "TX_GAB_SANS_ID":              ("accepted", "low",    "Transaction GAB acceptee malgre l'absence de gab_id"),
    "TX_NON_GAB_AVEC_ID":          ("accepted", "medium", "Transaction non-GAB acceptee malgre la presence d'un gab_id"),
    "CARTE_ACTIVE_COMPTE_CLOTURE": ("rejected", "high",   "Carte active sur compte cloture — rejetee"),
    "TX_COMPTE_INEXISTANT":        ("rejected", "high",   "Transaction sur compte inexistant — rejetee"),
    "CLIENT_AGENCE_FERMEE":        ("accepted", "medium", "Client accepte — transfert vers une agence active recommande"),
    "COMPTE_CLIENT_INEXISTANT":    ("rejected", "high",   "Compte sans client existant — rejete"),
    "DIGITAL_CLIENT_INEXISTANT":   ("rejected", "high",   "Usage digital sans client existant — rejete"),
    "CONTACT_INVALIDE":            ("rejected", "medium", "Client sans moyen de contact valide — rejete"),
}


def _count_cascade(table_name: str, record_id: int) -> dict:
    """Compte (sans rien inserer) les descendants qui seraient rejetes en cascade."""
    counts = {"comptes": 0, "transactions": 0, "cartes": 0, "digital_usage": 0}

    if table_name == "clients":
        comptes = query("SELECT compte_id FROM comptes WHERE client_id = :id", {"id": record_id})
        counts["comptes"] = len(comptes)
        for co in comptes:
            cid = co["compte_id"]
            counts["transactions"] += scalar("SELECT COUNT(*) FROM transactions WHERE compte_id = :id", {"id": cid}) or 0
            counts["cartes"]       += scalar("SELECT COUNT(*) FROM cartes WHERE compte_id = :id", {"id": cid}) or 0
        counts["digital_usage"] = scalar("SELECT COUNT(*) FROM digital_usage WHERE client_id = :id", {"id": record_id}) or 0

    elif table_name == "comptes":
        counts["transactions"] = scalar("SELECT COUNT(*) FROM transactions WHERE compte_id = :id", {"id": record_id}) or 0
        counts["cartes"]       = scalar("SELECT COUNT(*) FROM cartes WHERE compte_id = :id", {"id": record_id}) or 0

    counts["total"] = counts["comptes"] + counts["transactions"] + counts["cartes"] + counts["digital_usage"]
    return counts


@router.get("/cascade-preview")
def cascade_preview(rule_id: str, record_id: int):
    """Previsualise l'impact d'un rejet (combien de descendants seront rejetes)."""
    table_name = RULE_TABLE_MAP.get(rule_id)
    if not table_name:
        return {"total": 0, "details": {}}
    if table_name not in ("clients", "comptes"):
        return {"total": 0, "details": {}}
    counts = _count_cascade(table_name, record_id)
    return {
        "table": table_name,
        "record_id": record_id,
        "total": counts["total"],
        "details": {
            "comptes":       counts["comptes"],
            "transactions":  counts["transactions"],
            "cartes":        counts["cartes"],
            "digital_usage": counts["digital_usage"],
        },
    }


def _insert_decision(rule_id, table_name, record_id, decision, severity, comment, cascade_from=None):
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


def _cascade_reject(parent_rule_id, parent_table, parent_id, parent_decision_id):
    comment = f"Rejete en cascade depuis {parent_table} #{parent_id} (regle {parent_rule_id})"

    if parent_table == "clients":
        comptes = query("SELECT compte_id FROM comptes WHERE client_id = :id", {"id": parent_id})
        for co in comptes:
            cid = co["compte_id"]
            _insert_decision("COMPTE_CLIENT_INEXISTANT", "comptes", cid,
                             "rejected", "high", comment, parent_decision_id)
            for tx in query("SELECT transaction_id FROM transactions WHERE compte_id = :id", {"id": cid}):
                _insert_decision("TX_COMPTE_INEXISTANT", "transactions", tx["transaction_id"],
                                 "rejected", "high", comment, parent_decision_id)
            for ca in query("SELECT carte_id FROM cartes WHERE compte_id = :id", {"id": cid}):
                _insert_decision("CARTE_ACTIVE_COMPTE_CLOTURE", "cartes", ca["carte_id"],
                                 "rejected", "high", comment, parent_decision_id)
        for us in query("SELECT usage_id FROM digital_usage WHERE client_id = :id", {"id": parent_id}):
            _insert_decision("DIGITAL_CLIENT_INEXISTANT", "digital_usage", us["usage_id"],
                             "rejected", "high", comment, parent_decision_id)

    elif parent_table == "comptes":
        for tx in query("SELECT transaction_id FROM transactions WHERE compte_id = :id", {"id": parent_id}):
            _insert_decision("TX_COMPTE_INEXISTANT", "transactions", tx["transaction_id"],
                             "rejected", "high", comment, parent_decision_id)
        for ca in query("SELECT carte_id FROM cartes WHERE compte_id = :id", {"id": parent_id}):
            _insert_decision("CARTE_ACTIVE_COMPTE_CLOTURE", "cartes", ca["carte_id"],
                             "rejected", "high", comment, parent_decision_id)


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

    cascade_count = 0
    if body.decision == "rejected" and table_name in ("clients", "comptes"):
        try:
            dec_id = scalar(
                "SELECT MAX(id) FROM admin_decisions WHERE rule_id=:r AND record_id=:i AND cascade_from IS NULL",
                {"r": body.rule_id, "i": body.record_id}
            )
            before = scalar("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from = :d", {"d": dec_id}) or 0
            _cascade_reject(body.rule_id, table_name, body.record_id, dec_id)
            after = scalar("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from = :d", {"d": dec_id}) or 0
            cascade_count = after - before
        except Exception as e:
            print(f"[CASCADE] warning: {e}")

    return {"status": "ok", "decision": body.decision, "cascade_count": cascade_count}


@router.post("/bulk")
def bulk_decision(body: BulkDecisionIn):
    if body.rule_id not in RULE_TABLE_MAP:
        raise HTTPException(status_code=400, detail="Regle inconnue")
    auto = RULE_AUTO.get(body.rule_id)
    if not auto:
        raise HTTPException(status_code=400, detail="Regle sans decision auto")

    decision, severity, comment = (body.decision, body.severity, body.comment or auto[2])
    table_name = RULE_TABLE_MAP[body.rule_id]

    from app.routers.anomalies import RULES, _sample_pending
    rule = RULES.get(body.rule_id)
    if not rule:
        raise HTTPException(status_code=400, detail="Regle inconnue dans anomalies")

    records = _sample_pending(body.rule_id, rule, limit=10000, offset=0)
    count   = 0
    for rec in records:
        id_col = rule["id_col"].split(".")[-1]
        rec_id = rec.get(id_col) or rec.get(list(rec.keys())[0])
        try:
            _insert_decision(body.rule_id, table_name, rec_id, decision, severity, comment)
            if decision == "rejected" and table_name in ("clients", "comptes"):
                dec_id = scalar(
                    "SELECT MAX(id) FROM admin_decisions WHERE rule_id=:r AND record_id=:i AND cascade_from IS NULL",
                    {"r": body.rule_id, "i": rec_id}
                )
                _cascade_reject(body.rule_id, table_name, rec_id, dec_id)
            count += 1
        except Exception as e:
            print(f"[BULK] skip {rec_id}: {e}")

    return {"status": "ok", "processed": count, "decision": decision}


@router.get("/stats")
def get_stats():
    try:
        return {
            "total":         scalar("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NULL") or 0,
            "accepted":      scalar("SELECT COUNT(*) FROM admin_decisions WHERE decision='accepted' AND cascade_from IS NULL") or 0,
            "rejected":      scalar("SELECT COUNT(*) FROM admin_decisions WHERE decision='rejected' AND cascade_from IS NULL") or 0,
            "cascade":       scalar("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NOT NULL") or 0,
            "high_severity": scalar("SELECT COUNT(*) FROM admin_decisions WHERE severity='high' AND cascade_from IS NULL") or 0,
        }
    except Exception:
        return {"total": 0, "accepted": 0, "rejected": 0, "cascade": 0, "high_severity": 0}


@router.get("/cascade")
def list_cascade(
    limit:  int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0,  ge=0),
):
    """Liste des enregistrements rejetes EN CASCADE (cascade_from IS NOT NULL)."""
    try:
        total = scalar("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NOT NULL") or 0
        data  = query("""
            SELECT ad.id, ad.rule_id, ad.table_name, ad.record_id,
                   ad.decision, ad.severity, ad.comment, ad.decided_at,
                   ad.cascade_from,
                   parent.table_name AS parent_table,
                   parent.record_id  AS parent_record_id,
                   parent.rule_id    AS parent_rule
            FROM admin_decisions ad
            LEFT JOIN admin_decisions parent ON ad.cascade_from = parent.id
            WHERE ad.cascade_from IS NOT NULL
            ORDER BY ad.cascade_from DESC, ad.id DESC
            LIMIT :limit OFFSET :offset
        """, {"limit": limit, "offset": offset})
        return {"total": total, "data": data}
    except Exception as e:
        print(f"[DECISIONS] cascade list error: {e}")
        return {"total": 0, "data": []}


@router.get("/")
def list_decisions(
    limit:    int = Query(default=25, ge=1, le=100),
    offset:   int = Query(default=0,  ge=0),
    decision: Optional[str] = None,
    rule_id:  Optional[str] = None,
    severity: Optional[str] = None,
):
    where  = ["cascade_from IS NULL"]
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