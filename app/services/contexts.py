"""
Service des contextes de reporting
Al Barid Bank — Data Quality Platform

Le contexte de reporting est saisi par l'utilisateur. Sans controle, la meme
notion metier peut etre enregistree sous des formes differentes
(« analyse geographique », « Analyse Géographique », « ANALYSE-GEOGRAPHIQUE »),
ce qui fausserait a la fois les predictions du modele et le suivi de sa
performance.

Deux mecanismes previennent ce risque :
  1. NORMALISATION : toute saisie est ramenee a une forme canonique
     (majuscules, sans accents, underscores).
  2. REFERENTIEL : les contextes valides sont enregistres en base. La creation
     d'un nouveau contexte devient un acte volontaire et non un accident de
     frappe.
"""

import re
import unicodedata

from app.services.db import query, scalar


def normaliser(contexte: str) -> str:
    """
    Ramene une saisie libre a sa forme canonique.

      « analyse geographique »   -> ANALYSE_GEOGRAPHIQUE
      « Analyse Géographique »   -> ANALYSE_GEOGRAPHIQUE
      « ANALYSE-GEOGRAPHIQUE  »  -> ANALYSE_GEOGRAPHIQUE
    """
    if not contexte:
        return ""

    # Supprimer les accents
    texte = unicodedata.normalize("NFKD", contexte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))

    # Majuscules, espaces et tirets en underscores
    texte = texte.strip().upper()
    texte = re.sub(r"[\s\-]+", "_", texte)

    # Ne conserver que lettres, chiffres et underscores
    texte = re.sub(r"[^A-Z0-9_]", "", texte)

    # Reduire les underscores multiples et ceux en bordure
    texte = re.sub(r"_+", "_", texte).strip("_")

    return texte


def similarite(a: str, b: str) -> float:
    """
    Similarite entre deux chaines (0 a 1), fondee sur la distance d'edition.
    Sert a detecter les fautes de frappe proches d'un contexte existant.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    # Distance de Levenshtein
    m, n = len(a), len(b)
    precedente = list(range(n + 1))
    for i in range(1, m + 1):
        courante = [i] + [0] * n
        for j in range(1, n + 1):
            cout = 0 if a[i - 1] == b[j - 1] else 1
            courante[j] = min(
                precedente[j] + 1,        # suppression
                courante[j - 1] + 1,      # insertion
                precedente[j - 1] + cout  # substitution
            )
        precedente = courante

    distance = precedente[n]
    return 1.0 - distance / max(m, n)


def lister() -> list[dict]:
    """Contextes du referentiel, du plus utilise au moins utilise."""
    try:
        return query("""
            SELECT contexte, description, is_trained, usage_count, created_at
            FROM reporting_contexts
            ORDER BY is_trained DESC, usage_count DESC, contexte
        """)
    except Exception as e:
        print(f"[CONTEXTS] Referentiel indisponible : {e}")
        return []


def existe(contexte: str) -> bool:
    """Indique si un contexte (deja normalise) figure au referentiel."""
    try:
        n = scalar(
            "SELECT COUNT(*) FROM reporting_contexts WHERE contexte = :c",
            {"c": contexte}
        )
        return bool(n)
    except Exception:
        return False


def suggerer_proche(contexte: str, seuil: float = 0.80) -> str | None:
    """
    Cherche au referentiel un contexte tres proche de la saisie, afin de
    detecter une faute de frappe. Renvoie le contexte suggere, ou None.
    """
    meilleur, score_max = None, 0.0
    for ligne in lister():
        score = similarite(contexte, ligne["contexte"])
        if score > score_max:
            meilleur, score_max = ligne["contexte"], score

    if meilleur and seuil <= score_max < 1.0:
        return meilleur
    return None


def creer(contexte: str, description: str = "") -> dict:
    """Enregistre un nouveau contexte au referentiel (creation volontaire)."""
    contexte = normaliser(contexte)
    if not contexte:
        raise ValueError("Contexte invalide.")

    query("""
        INSERT INTO reporting_contexts (contexte, description, is_trained)
        VALUES (:c, :d, FALSE)
        ON CONFLICT (contexte) DO NOTHING
    """, {"c": contexte, "d": description or ""})

    return {"contexte": contexte, "cree": True}


def incrementer_usage(contexte: str) -> None:
    """Comptabilise une utilisation du contexte (statistiques d'usage)."""
    try:
        query("""
            UPDATE reporting_contexts
            SET usage_count = usage_count + 1, last_used_at = NOW()
            WHERE contexte = :c
        """, {"c": contexte})
    except Exception as e:
        print(f"[CONTEXTS] Usage non comptabilise : {e}")


def initialiser(contextes_modele: list[str]) -> None:
    """
    Amorce le referentiel avec les contextes sur lesquels le modele a ete
    entraine. Appele au demarrage de l'application.
    """
    for c in contextes_modele:
        try:
            query("""
                INSERT INTO reporting_contexts (contexte, description, is_trained)
                VALUES (:c, :d, TRUE)
                ON CONFLICT (contexte) DO UPDATE SET is_trained = TRUE
            """, {"c": c, "d": "Contexte d'entrainement du modele"})
        except Exception as e:
            print(f"[CONTEXTS] Initialisation ({c}) : {e}")
