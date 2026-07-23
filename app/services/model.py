"""
Service de prediction ML
Al Barid Bank — Data Quality Platform

Charge le modele entraine (Foret aleatoire) et expose une fonction de prediction.
Le modele predit la decision (accepted / rejected) a partir de :
  - rule_id            : la regle violee
  - table_origine      : l'entite d'origine
  - contexte_reporting : l'objectif du rapport (choisi par l'utilisateur)
  - valeur_metier      : l'attribut metier continu (montant, anciennete, ...)

IMPORTANT : l'encodage doit reproduire EXACTEMENT celui de l'entrainement.
La liste des colonnes du modele (colonnes_modele.pkl) garantit cette coherence :
les colonnes sont reconstruites dans le meme ordre, les colonnes absentes
(categories jamais vues, ex. un nouveau contexte) sont mises a zero.
"""

import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = os.path.join("app", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "modele_qualite.pkl")
COLUMNS_PATH = os.path.join(MODEL_DIR, "colonnes_modele.pkl")

# Charges une seule fois au demarrage
_model = None
_columns = None
_load_error = None


def load_model():
    """Charge le modele et la liste des colonnes. Appele au demarrage de l'app."""
    global _model, _columns, _load_error
    try:
        _model = joblib.load(MODEL_PATH)
        _columns = joblib.load(COLUMNS_PATH)
        _load_error = None
        print(f"[MODEL] Modele charge : {type(_model).__name__} "
              f"({len(_columns)} variables)")
    except Exception as e:
        _model = None
        _columns = None
        _load_error = str(e)
        print(f"[MODEL] Impossible de charger le modele : {e}")


def is_ready() -> bool:
    """Indique si le modele est disponible."""
    return _model is not None and _columns is not None


def get_status() -> dict:
    """Etat du service de prediction."""
    return {
        "ready": is_ready(),
        "model_type": type(_model).__name__ if _model is not None else None,
        "n_features": len(_columns) if _columns else 0,
        "error": _load_error,
    }


def _build_features(rule_id: str, table_origine: str,
                    contexte_reporting: str, valeur_metier: float) -> pd.DataFrame:
    """
    Construit le vecteur de variables attendu par le modele.

    Reproduit l'encodage one-hot de l'entrainement :
      - une colonne par categorie, nommee '<variable>_<valeur>'
      - toutes les colonnes du modele sont presentes, dans le meme ordre
      - les categories inconnues du modele (ex. nouveau contexte) laissent
        simplement toutes leurs colonnes a zero : le modele predira alors
        sur la seule base des autres variables.
    """
    # Toutes les colonnes a zero au depart
    ligne = {col: 0 for col in _columns}

    # Variable numerique conservee telle quelle
    if "valeur_metier" in ligne:
        ligne["valeur_metier"] = float(valeur_metier)

    # Variables categorielles : on active la colonne correspondante si elle existe
    for prefixe, valeur in (
        ("rule_id", rule_id),
        ("table_origine", table_origine),
        ("contexte_reporting", contexte_reporting),
    ):
        colonne = f"{prefixe}_{valeur}"
        if colonne in ligne:
            ligne[colonne] = 1

    # DataFrame a une ligne, colonnes dans l'ordre exact du modele
    return pd.DataFrame([ligne], columns=_columns)


def predict(rule_id: str, table_origine: str,
            contexte_reporting: str, valeur_metier: float) -> dict:
    """
    Predit la decision pour un enregistrement dans un contexte donne.

    Retourne :
      - prediction   : 'accepted' ou 'rejected'
      - proba_rejet  : probabilite que l'enregistrement soit rejete (0 a 1)
      - confiance    : probabilite de la classe predite (0 a 1)
      - contexte_connu : False si le contexte n'a jamais ete vu a l'entrainement
    """
    if not is_ready():
        raise RuntimeError("Le modele n'est pas disponible.")

    X = _build_features(rule_id, table_origine, contexte_reporting, valeur_metier)

    # Classe positive (1) = rejected, conformement a l'entrainement
    proba_rejet = float(_model.predict_proba(X)[0][1])
    prediction = "rejected" if proba_rejet >= 0.5 else "accepted"
    confiance = proba_rejet if prediction == "rejected" else 1.0 - proba_rejet

    # Le contexte est-il connu du modele ?
    contexte_connu = f"contexte_reporting_{contexte_reporting}" in _columns

    return {
        "prediction": prediction,
        "proba_rejet": round(proba_rejet, 4),
        "confiance": round(confiance, 4),
        "contexte_connu": contexte_connu,
    }


def contextes_connus() -> list[str]:
    """Liste des contextes sur lesquels le modele a ete entraine."""
    if not _columns:
        return []
    prefixe = "contexte_reporting_"
    return sorted(
        col[len(prefixe):] for col in _columns if col.startswith(prefixe)
    )
