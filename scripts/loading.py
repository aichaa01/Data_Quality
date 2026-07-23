"""
Chargement des donnees
Al Barid Bank — Data Quality Platform

La base relationnelle ne porte que l'ETAT COURANT. Le chargement suit deux
strategies selon la nature de l'entite :

  * Entites a etat evolutif (clients, comptes, cartes) -> UPSERT.
    Si l'enregistrement existe deja (meme cle), il est mis a jour : la nouvelle
    version ECRASE l'ancienne. Aucun historique n'est conserve dans la base
    relationnelle. L'historisation releve de l'entrepot, au moyen d'un snapshot
    dbt qui capture les versions successives.

  * Evenements immuables (transactions, digital_usage, agences, gabs) -> AJOUT.
    Un evenement passe ne change jamais.

Un enregistrement mis a jour repasse par la detection au prochain cycle dbt,
comme un nouvel enregistrement. Les decisions prises sur ses versions
anterieures sont conservees.
"""

import os

import pandas as pd
from sqlalchemy import create_engine, text

# Entites a etat evolutif : upsert (la nouvelle version ecrase l'ancienne)
ENTITES_UPSERT = {
    "clients": {
        "cle": "client_id",
        "colonnes": ["client_id", "cin", "nom", "prenom", "date_naissance",
                     "telephone", "email", "adresse", "agence_id", "date_creation"],
    },
    "comptes": {
        "cle": "compte_id",
        "colonnes": ["compte_id", "client_id", "type_compte",
                     "date_ouverture", "solde", "statut"],
    },
    "cartes": {
        "cle": "carte_id",
        "colonnes": ["carte_id", "compte_id", "type_carte",
                     "date_expiration", "statut"],
    },
}

# Evenements immuables : ajout simple
ENTITES_EVENEMENTS = {"transactions", "digital_usage", "agences", "gabs"}

DATE_COLS = {
    "agences":       ["date_ouverture", "date_fermeture"],
    "clients":       ["date_naissance", "date_creation"],
    "comptes":       ["date_ouverture"],
    "cartes":        ["date_expiration"],
    "transactions":  ["date_transaction"],
    "digital_usage": ["date_connexion"],
}

DTYPE_OVERRIDE = {
    "clients": {"telephone": "string", "cin": "string"},
}


def get_engine():
    url = (f"postgresql+psycopg2://{os.getenv('POSTGRES_USER', 'admin')}:"
           f"{os.getenv('POSTGRES_PASSWORD', 'admin123')}@"
           f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
           f"{os.getenv('POSTGRES_PORT', '5432')}/"
           f"{os.getenv('POSTGRES_DB', 'barid_bank')}")
    return create_engine(url)


def _lire_csv(chemin: str, entite: str) -> pd.DataFrame:
    df = pd.read_csv(
        chemin,
        parse_dates=DATE_COLS.get(entite, []),
        dtype=DTYPE_OVERRIDE.get(entite, {}),
        low_memory=False,
    )
    df = df.where(pd.notna(df), None)
    return df.replace("", None)


def charger_evenements(engine, entite: str, df: pd.DataFrame) -> int:
    """Ajout simple, pour les entites immuables."""
    df.to_sql(entite, engine, if_exists="append", index=False,
              chunksize=1000, method="multi")
    print(f"  {entite:14s} (ajout)   {len(df):>7d} lignes")
    return len(df)


def charger_upsert(engine, entite: str, df: pd.DataFrame) -> dict:
    """
    Upsert : la nouvelle version ecrase l'ancienne (etat courant uniquement).
    Repose sur « INSERT ... ON CONFLICT (cle) DO UPDATE », natif a PostgreSQL.
    """
    cfg = ENTITES_UPSERT[entite]
    cle = cfg["cle"]
    colonnes = cfg["colonnes"]

    cols = ", ".join(colonnes)
    params = ", ".join(f":{c}" for c in colonnes)
    maj = ", ".join(f"{c} = EXCLUDED.{c}" for c in colonnes if c != cle)

    requete = text(
        f"INSERT INTO {entite} ({cols}) VALUES ({params}) "
        f"ON CONFLICT ({cle}) DO UPDATE SET {maj}"
    )

    with engine.begin() as conn:
        for _, ligne in df.iterrows():
            conn.execute(requete, {c: ligne.get(c) for c in colonnes})

    print(f"  {entite:14s} (upsert)  {len(df):>7d} lignes (etat courant)")
    return {"lignes": len(df)}


def charger_fichier(engine, entite: str, chemin: str) -> dict:
    """Aiguille un fichier vers la bonne strategie de chargement."""
    df = _lire_csv(chemin, entite)

    if entite in ENTITES_UPSERT:
        charger_upsert(engine, entite, df)
        return {"entite": entite, "mode": "upsert", "lignes": len(df)}

    if entite in ENTITES_EVENEMENTS:
        n = charger_evenements(engine, entite, df)
        return {"entite": entite, "mode": "ajout", "lignes": n}

    raise ValueError(f"Entite inconnue : {entite}")