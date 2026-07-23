"""
Service de calcul des variables metier
Al Barid Bank — Data Quality Platform

Le modele attend une variable 'valeur_metier' dont la signification depend de la
regle violee. Cette logique reproduit exactement celle utilisee lors de la
construction du jeu de donnees d'entrainement :

  - TX_GAB_SANS_ID, TX_NON_GAB_AVEC_ID   -> montant de la transaction
  - CLIENT_AGENCE_FERMEE                 -> anciennete du client (annees)
  - DIGITAL_CLIENT_INEXISTANT            -> anciennete de la connexion (annees)
  - CARTE_ACTIVE_COMPTE_CLOTURE          -> delai avant expiration (annees)
  - autres regles (regles dures, CONTACT_INVALIDE) -> 0

Toute divergence avec l'entrainement fausserait la prediction.
"""

from app.services.db import scalar

# Requete SQL renvoyant la valeur metier, par regle.
# :record_id est l'identifiant de l'enregistrement concerne.
VALEUR_METIER_SQL = {
    "TX_GAB_SANS_ID": """
        SELECT COALESCE(montant, 0)
        FROM transactions WHERE transaction_id = :record_id
    """,
    "TX_NON_GAB_AVEC_ID": """
        SELECT COALESCE(montant, 0)
        FROM transactions WHERE transaction_id = :record_id
    """,
    "CLIENT_AGENCE_FERMEE": """
        SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - date_creation)) / 31557600, 0)
        FROM clients WHERE client_id = :record_id
    """,
    "DIGITAL_CLIENT_INEXISTANT": """
        SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - date_connexion)) / 31557600, 0)
        FROM digital_usage WHERE usage_id = :record_id
    """,
    "CARTE_ACTIVE_COMPTE_CLOTURE": """
        SELECT COALESCE(EXTRACT(EPOCH FROM (date_expiration - NOW())) / 31557600, 0)
        FROM cartes WHERE carte_id = :record_id
    """,
}

# Regles sans zone de gris : la valeur metier vaut 0 a l'entrainement
VALEUR_METIER_NULLE = {
    "TX_COMPTE_INEXISTANT",
    "COMPTE_CLIENT_INEXISTANT",
    "CONTACT_INVALIDE",
}


def get_valeur_metier(rule_id: str, record_id: int) -> float:
    """
    Calcule la valeur metier d'un enregistrement selon la regle violee.
    Renvoie 0.0 pour les regles sans zone de gris, ou en cas d'absence de donnee.
    """
    if rule_id in VALEUR_METIER_NULLE:
        return 0.0

    sql = VALEUR_METIER_SQL.get(rule_id)
    if sql is None:
        return 0.0

    try:
        valeur = scalar(sql, {"record_id": record_id})
        return round(float(valeur), 2) if valeur is not None else 0.0
    except Exception as e:
        print(f"[FEATURES] valeur_metier indisponible ({rule_id}, {record_id}) : {e}")
        return 0.0
