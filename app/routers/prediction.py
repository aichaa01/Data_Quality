"""
Router Prediction — suggestion du modele ML
Al Barid Bank — Data Quality Platform

Le modele suggere une decision (accepted / rejected) pour un enregistrement
en anomalie, dans un contexte de reporting donne. La suggestion est affichee
au reporter et enregistree dans la table de suivi, afin de pouvoir ensuite la
comparer a la decision finalement prise et suivre la performance du modele
dans le temps.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import model as ml
from app.services import contexts
from app.services.features import get_valeur_metier
from app.services.db import query

router = APIRouter(prefix="/api/prediction", tags=["prediction"])

# Table d'origine de chaque regle (identique au reste de l'application)
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


class PredictionIn(BaseModel):
    rule_id:            str
    record_id:          int
    contexte_reporting: str


@router.get("/status")
def status():
    """Etat du modele et contextes sur lesquels il a ete entraine."""
    etat = ml.get_status()
    etat["contextes_connus"] = ml.contextes_connus()
    return etat


class ContexteIn(BaseModel):
    contexte:    str
    description: Optional[str] = None


@router.get("/contextes")
def liste_contextes():
    """Referentiel des contextes de reporting."""
    return {"contextes": contexts.lister()}


@router.post("/contextes")
def creer_contexte(payload: ContexteIn):
    """
    Cree un nouveau contexte au referentiel.
    La creation est un acte volontaire : elle previent les doublons nes de
    fautes de frappe ou de variantes d'ecriture.
    """
    normalise = contexts.normaliser(payload.contexte)
    if not normalise:
        raise HTTPException(status_code=400, detail="Contexte invalide.")

    if contexts.existe(normalise):
        return {"contexte": normalise, "cree": False, "message": "Ce contexte existe deja."}

    contexts.creer(normalise, payload.description or "")
    return {"contexte": normalise, "cree": True}


@router.get("/contextes/verifier")
def verifier_contexte(contexte: str):
    """
    Verifie une saisie avant creation : renvoie la forme normalisee, indique si
    le contexte existe deja, et signale un contexte proche (faute de frappe
    probable).
    """
    normalise = contexts.normaliser(contexte)
    if not normalise:
        return {"valide": False, "message": "Contexte invalide."}

    if contexts.existe(normalise):
        return {"valide": True, "normalise": normalise, "existe": True, "suggestion": None}

    suggestion = contexts.suggerer_proche(normalise)
    return {
        "valide": True,
        "normalise": normalise,
        "existe": False,
        "suggestion": suggestion,
    }


@router.post("")
def predire(payload: PredictionIn):
    """
    Predit la decision pour un enregistrement dans un contexte donne,
    puis enregistre la suggestion dans la table de suivi.
    """
    if not ml.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Le modele de prediction n'est pas disponible."
        )

    rule_id = payload.rule_id
    record_id = payload.record_id

    # Normalisation : les variantes d'ecriture d'un meme contexte convergent
    # vers une forme canonique unique.
    contexte = contexts.normaliser(payload.contexte_reporting)

    if not contexte:
        raise HTTPException(status_code=400, detail="Le contexte est obligatoire.")

    # Le contexte doit figurer au referentiel : la creation d'un nouveau
    # contexte est un acte volontaire, effectue via /api/prediction/contextes.
    if not contexts.existe(contexte):
        raise HTTPException(
            status_code=400,
            detail=f"Le contexte '{contexte}' n'existe pas. Creez-le d'abord."
        )

    table_origine = RULE_TABLE_MAP.get(rule_id)
    if table_origine is None:
        raise HTTPException(status_code=400, detail=f"Regle inconnue : {rule_id}")

    # Variable metier, calculee exactement comme a l'entrainement
    valeur_metier = get_valeur_metier(rule_id, record_id)

    try:
        resultat = ml.predict(rule_id, table_origine, contexte, valeur_metier)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Echec de la prediction : {e}")

    # Enregistrement de la suggestion (la decision du reporter viendra plus tard)
    try:
        query("""
            INSERT INTO model_predictions
                (table_origine, record_id, rule_id, contexte_reporting,
                 valeur_metier, prediction_modele, proba_rejet, contexte_connu)
            VALUES
                (:table_origine, :record_id, :rule_id, :contexte,
                 :valeur_metier, :prediction, :proba, :contexte_connu)
        """, {
            "table_origine":  table_origine,
            "record_id":      record_id,
            "rule_id":        rule_id,
            "contexte":       contexte,
            "valeur_metier":  valeur_metier,
            "prediction":     resultat["prediction"],
            "proba":          resultat["proba_rejet"],
            "contexte_connu": resultat["contexte_connu"],
        })
    except Exception as e:
        # La prediction reste utilisable meme si le suivi echoue
        print(f"[PREDICTION] Suivi non enregistre : {e}")

    contexts.incrementer_usage(contexte)

    return {
        "rule_id":            rule_id,
        "record_id":          record_id,
        "table_origine":      table_origine,
        "contexte_reporting": contexte,
        "valeur_metier":      valeur_metier,
        **resultat,
    }