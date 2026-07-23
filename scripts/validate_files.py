"""
Validation structurelle des fichiers entrants
Al Barid Bank — Data Quality Platform

IMPORTANT — distinction fondamentale :

  * VALIDATION STRUCTURELLE (ce module) : le fichier est-il exploitable ?
    Est-il lisible, non vide, dote des colonnes attendues, rattachable a une
    entite connue ? Un echec ici signifie que le fichier est INUTILISABLE :
    il est ecarte vers le compartiment de rejet.

  * REGLES METIER (dbt, en aval) : les donnees contiennent-elles des anomalies ?
    Un fichier rempli d'anomalies est parfaitement NORMAL — c'est precisement
    l'objet de la plateforme. Ces anomalies sont detectees apres chargement et
    soumises a la decision d'un reporter.

Un fichier n'est donc JAMAIS rejete parce qu'il contient des anomalies.
Il n'est rejete que s'il est structurellement inexploitable.

L'orchestration (telechargement depuis le stockage objet, deplacement entre
compartiments) releve du DAG d'ingestion et du service de stockage. Ce module
se limite a la validation elle-meme.
"""

import os

import pandas as pd

# ─────────────────────────────────────────────
# Colonnes attendues par entite (schema de reference)
# ─────────────────────────────────────────────
SCHEMAS = {
    "agences": [
        "agence_id", "nom_agence", "ville", "region",
        "date_ouverture", "type_agence", "statut", "date_fermeture",
    ],
    "clients": [
        "client_id", "cin", "nom", "prenom", "date_naissance",
        "telephone", "email", "adresse", "agence_id", "date_creation",
    ],
    "comptes": [
        "compte_id", "client_id", "type_compte",
        "date_ouverture", "solde", "statut",
    ],
    "cartes": [
        "carte_id", "compte_id", "type_carte", "date_expiration", "statut",
    ],
    "gabs": [
        "gab_id", "agence_id", "type_gab", "ville", "statut",
    ],
    "transactions": [
        "transaction_id", "compte_id", "date_transaction", "montant",
        "type_transaction", "canal", "agence_id", "gab_id",
    ],
    "digital_usage": [
        "usage_id", "client_id", "date_connexion", "canal", "action",
    ],
}


def identifier_entite(nom_fichier: str) -> str | None:
    """
    Deduit l'entite a partir du nom du fichier.
    Accepte 'clients.csv', 'clients_20260713.csv', 'CLIENTS-batch2.csv', ...
    """
    base = os.path.basename(nom_fichier).lower().replace(".csv", "")
    for entite in SCHEMAS:
        if base == entite or base.startswith(entite + "_") or base.startswith(entite + "-"):
            return entite
    return None


def valider(chemin: str) -> dict:
    """
    Valide structurellement un fichier deja rapatrie localement.
    Retourne un rapport : {valide, entite, lignes, erreurs, avertissements}
    """
    rapport = {
        "fichier":        os.path.basename(chemin),
        "valide":         False,
        "entite":         None,
        "lignes":         0,
        "erreurs":        [],
        "avertissements": [],
    }

    # 1. Le fichier est-il rattachable a une entite connue ?
    entite = identifier_entite(chemin)
    if entite is None:
        rapport["erreurs"].append(
            "Entite indeterminee : le nom du fichier ne correspond a aucune "
            f"entite connue ({', '.join(SCHEMAS)})."
        )
        return rapport
    rapport["entite"] = entite

    # 2. Le fichier est-il lisible ?
    try:
        df = pd.read_csv(chemin, dtype=str, keep_default_na=False, na_values=[""])
    except Exception as e:
        rapport["erreurs"].append(f"Fichier illisible : {e}")
        return rapport

    # 3. Le fichier est-il vide ?
    if len(df) == 0:
        rapport["erreurs"].append("Fichier vide : aucune ligne de donnees.")
        return rapport
    rapport["lignes"] = len(df)

    # 4. Les colonnes attendues sont-elles presentes ?
    attendues = set(SCHEMAS[entite])
    presentes = set(df.columns)

    manquantes = attendues - presentes
    if manquantes:
        rapport["erreurs"].append(
            f"Colonnes manquantes : {', '.join(sorted(manquantes))}"
        )
        return rapport

    # 5. Colonnes surnumeraires : simple avertissement, non un rejet
    superflues = presentes - attendues
    if superflues:
        rapport["avertissements"].append(
            f"Colonnes ignorees (absentes du schema) : {', '.join(sorted(superflues))}"
        )

    # 6. La cle primaire est-elle renseignee ?
    #    Une cle absente rend l'enregistrement inidentifiable : c'est structurel.
    cle = SCHEMAS[entite][0]
    cles_vides = int(df[cle].isna().sum())
    if cles_vides > 0:
        rapport["erreurs"].append(
            f"Cle primaire '{cle}' non renseignee sur {cles_vides} ligne(s)."
        )
        return rapport

    # NOTE : aucune verification metier ici. Les valeurs manquantes, les
    # incoherences et les doublons sont ATTENDUS : ils seront detectes en aval
    # par les regles de qualite et soumis a la decision d'un reporter.

    rapport["valide"] = True
    return rapport