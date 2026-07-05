"""
Router Dashboard — KPIs uniquement sur anomalies EN ATTENTE
Une fois decidee (directe ou cascade), une anomalie disparait du dashboard.
"""

from fastapi import APIRouter
from app.services.db import scalar

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _excl(rule_id, id_col):
    return (f"NOT EXISTS (SELECT 1 FROM admin_decisions ad "
            f"WHERE ad.rule_id='{rule_id}' AND ad.record_id={id_col})")


PENDING = {
    "TX_GAB_SANS_ID": ("coherence",
        f"SELECT COUNT(*) FROM transactions "
        f"WHERE canal='GAB' AND gab_id IS NULL AND {_excl('TX_GAB_SANS_ID','transaction_id')}"),

    "TX_NON_GAB_AVEC_ID": ("coherence",
        f"SELECT COUNT(*) FROM transactions "
        f"WHERE canal!='GAB' AND gab_id IS NOT NULL AND {_excl('TX_NON_GAB_AVEC_ID','transaction_id')}"),

    "CARTE_ACTIVE_COMPTE_CLOTURE": ("coherence",
        f"SELECT COUNT(*) FROM cartes c JOIN comptes co ON c.compte_id=co.compte_id "
        f"WHERE c.statut='active' AND co.statut='cloture' AND {_excl('CARTE_ACTIVE_COMPTE_CLOTURE','c.carte_id')}"),

    "TX_COMPTE_INEXISTANT": ("coherence",
        f"SELECT COUNT(*) FROM transactions t "
        f"WHERE NOT EXISTS (SELECT 1 FROM comptes c WHERE c.compte_id=t.compte_id) "
        f"AND {_excl('TX_COMPTE_INEXISTANT','t.transaction_id')}"),

    "CLIENT_AGENCE_FERMEE": ("coherence",
        f"SELECT COUNT(*) FROM clients cl JOIN agences a ON cl.agence_id=a.agence_id "
        f"WHERE a.statut='fermee' AND {_excl('CLIENT_AGENCE_FERMEE','cl.client_id')}"),

    "COMPTE_CLIENT_INEXISTANT": ("coherence",
        f"SELECT COUNT(*) FROM comptes co "
        f"WHERE NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id=co.client_id) "
        f"AND {_excl('COMPTE_CLIENT_INEXISTANT','co.compte_id')}"),

    "DIGITAL_CLIENT_INEXISTANT": ("coherence",
        f"SELECT COUNT(*) FROM digital_usage du "
        f"WHERE NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id=du.client_id) "
        f"AND {_excl('DIGITAL_CLIENT_INEXISTANT','du.usage_id')}"),

    "CONTACT_INVALIDE": ("exactitude",
        f"SELECT COUNT(*) FROM clients "
        f"WHERE telephone IS NULL AND (email IS NULL OR email NOT LIKE '%@%' OR email NOT LIKE '%.%') "
        f"AND {_excl('CONTACT_INVALIDE','client_id')}"),
}


def _safe(sql):
    try:
        return scalar(sql) or 0
    except Exception:
        return 0


@router.get("/kpis")
def get_kpis():
    tables = ["agences", "clients", "comptes", "cartes", "gabs", "transactions", "digital_usage"]
    total  = sum(_safe(f"SELECT COUNT(*) FROM {t}") for t in tables)
    en_attente = sum(_safe(sql) for _, sql in PENDING.values())
    traites    = _safe("SELECT COUNT(*) FROM admin_decisions WHERE cascade_from IS NULL")
    return {
        "total_enregistrements": total,
        "total_anomalies":       en_attente,
        "en_attente":            en_attente,
        "traites":               traites,
    }


@router.get("/anomalies-par-dimension")
def get_par_dimension():
    totals = {}
    for rule_id, (dim, sql) in PENDING.items():
        c = _safe(sql)
        totals[dim] = totals.get(dim, 0) + c
    return [{"dimension": d, "count": c} for d, c in totals.items() if c > 0]


@router.get("/anomalies-par-regle")
def get_par_regle():
    result = []
    for rule_id, (dim, sql) in PENDING.items():
        c = _safe(sql)
        if c > 0:
            result.append({"rule_id": rule_id, "dimension": dim, "en_attente": c})
    return sorted(result, key=lambda x: x["en_attente"], reverse=True)