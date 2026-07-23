"""
Generation du dataset ML — NIVEAU 2 (contexte de reporting + zone de gris + cascade)
Al Barid Bank — Data Quality Platform

Schema de sortie (identique a l'ancien fct_quality + 2 nouvelles colonnes) :
  table_origine, record_id, rule_id, dimension, severity, label,
  decision_type, is_valide, date_id, dq_score,
  contexte_reporting (NOUVEAU), valeur_metier (NOUVEAU)

Principe
--------
La decision depend de : rule_id x contexte_reporting x attribut metier (+ bruit).
Chaque enregistrement (anomalie ou valide) est evalue dans les 3 contextes.
La CASCADE est recalculee PAR CONTEXTE : si un parent est rejete dans un
contexte donne, ses descendants sont rejetes en cascade dans ce meme contexte.

Sortie : data/ml/ml_dataset_v2.csv
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text

POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB", "barid_bank")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin123")

OUTPUT_PATH = "data/ml/ml_dataset_v2.csv"

np.random.seed(42)
BRUIT = 0.08
CONTEXTES = ["CAMPAGNE_CONTACT", "ANALYSE_GEOGRAPHIQUE", "ANALYSE_TRANSACTIONNELLE"]
NOW = pd.Timestamp(datetime.now())

# ─────────────────────────────────────────────
# Metadonnees des regles : dimension + severity type (comme l'ancien schema)
# ─────────────────────────────────────────────
META = {
    "CONTACT_INVALIDE":            {"dimension": "exactitude", "severity": "medium"},
    "CLIENT_AGENCE_FERMEE":        {"dimension": "coherence",  "severity": "medium"},
    "COMPTE_CLIENT_INEXISTANT":    {"dimension": "coherence",  "severity": "high"},
    "CARTE_ACTIVE_COMPTE_CLOTURE": {"dimension": "coherence",  "severity": "high"},
    "TX_COMPTE_INEXISTANT":        {"dimension": "coherence",  "severity": "high"},
    "TX_GAB_SANS_ID":              {"dimension": "coherence",  "severity": "low"},
    "TX_NON_GAB_AVEC_ID":          {"dimension": "coherence",  "severity": "medium"},
    "DIGITAL_CLIENT_INEXISTANT":   {"dimension": "coherence",  "severity": "high"},
    "AUCUNE":                      {"dimension": "aucune",     "severity": "low"},
}

# dq_score derive de la severity (comme l'ancien schema : 100/85/60/25)
DQ_SCORE = {"low": 85, "medium": 60, "high": 25}


def get_engine():
    url = (f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
           f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    return create_engine(url)


def anciennete_annees(serie):
    d = pd.to_datetime(serie, errors="coerce")
    return (NOW - d).dt.days / 365.25

def jours_avant(serie):
    d = pd.to_datetime(serie, errors="coerce")
    return (d - NOW).dt.days

def bruiter_array(decisions):
    """Applique le bruit sur un array de decisions (vectorise)."""
    mask = np.random.random(len(decisions)) < BRUIT
    inverse = np.where(np.array(decisions) == "accepted", "rejected", "accepted")
    return np.where(mask, inverse, decisions)


# ─────────────────────────────────────────────
# Detection des anomalies (+ attributs metier + date + parents pour cascade)
# ─────────────────────────────────────────────
DETECTION = {
    "TX_COMPTE_INEXISTANT": {
        "table": "transactions",
        "sql": """
            SELECT t.transaction_id AS record_id, t.montant AS attr,
                   t.date_transaction AS date_ref, t.compte_id AS parent_compte
            FROM transactions t
            WHERE NOT EXISTS (SELECT 1 FROM comptes c WHERE c.compte_id = t.compte_id)
        """,
    },
    "COMPTE_CLIENT_INEXISTANT": {
        "table": "comptes",
        "sql": """
            SELECT co.compte_id AS record_id, co.solde AS attr,
                   co.date_ouverture AS date_ref, co.client_id AS parent_client
            FROM comptes co
            WHERE NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = co.client_id)
        """,
    },
    "DIGITAL_CLIENT_INEXISTANT": {
        "table": "digital_usage",
        "sql": """
            SELECT du.usage_id AS record_id, NULL::numeric AS attr,
                   du.date_connexion AS date_ref, du.client_id AS parent_client
            FROM digital_usage du
            WHERE NOT EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = du.client_id)
        """,
        "date_is_conn": True,
    },
    "CONTACT_INVALIDE": {
        "table": "clients",
        "sql": """
            SELECT cl.client_id AS record_id, NULL::numeric AS attr,
                   cl.date_creation AS date_ref
            FROM clients cl
            WHERE cl.telephone IS NULL
              AND (cl.email IS NULL OR cl.email NOT LIKE '%@%' OR cl.email NOT LIKE '%.%')
        """,
        "attr_from_date": True,
    },
    "CLIENT_AGENCE_FERMEE": {
        "table": "clients",
        "sql": """
            SELECT cl.client_id AS record_id, NULL::numeric AS attr,
                   cl.date_creation AS date_ref
            FROM clients cl JOIN agences a ON cl.agence_id = a.agence_id
            WHERE a.statut = 'fermee'
        """,
        "attr_from_date": True,
    },
    "CARTE_ACTIVE_COMPTE_CLOTURE": {
        "table": "cartes",
        "sql": """
            SELECT c.carte_id AS record_id, NULL::numeric AS attr,
                   c.date_expiration AS date_ref
            FROM cartes c JOIN comptes co ON c.compte_id = co.compte_id
            WHERE c.statut = 'active' AND co.statut = 'cloture'
        """,
        "attr_from_expir": True,
    },
    "TX_GAB_SANS_ID": {
        "table": "transactions",
        "sql": """
            SELECT transaction_id AS record_id, montant AS attr,
                   date_transaction AS date_ref
            FROM transactions
            WHERE canal = 'GAB' AND gab_id IS NULL
        """,
    },
    "TX_NON_GAB_AVEC_ID": {
        "table": "transactions",
        "sql": """
            SELECT transaction_id AS record_id, montant AS attr,
                   date_transaction AS date_ref
            FROM transactions
            WHERE canal != 'GAB' AND gab_id IS NOT NULL
        """,
    },
}

VALIDES = {
    "clients": """
        SELECT cl.client_id AS record_id, cl.date_creation AS date_ref
        FROM clients cl
        WHERE NOT (cl.telephone IS NULL
              AND (cl.email IS NULL OR cl.email NOT LIKE '%@%' OR cl.email NOT LIKE '%.%'))
          AND NOT EXISTS (SELECT 1 FROM agences a
                          WHERE a.agence_id = cl.agence_id AND a.statut = 'fermee')
    """,
    "comptes": """
        SELECT co.compte_id AS record_id, co.date_ouverture AS date_ref
        FROM comptes co
        WHERE EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = co.client_id)
    """,
    "cartes": """
        SELECT c.carte_id AS record_id, c.date_expiration AS date_ref
        FROM cartes c JOIN comptes co ON c.compte_id = co.compte_id
        WHERE NOT (c.statut = 'active' AND co.statut = 'cloture')
    """,
    "transactions": """
        SELECT t.transaction_id AS record_id, t.date_transaction AS date_ref
        FROM transactions t
        WHERE EXISTS (SELECT 1 FROM comptes c WHERE c.compte_id = t.compte_id)
          AND NOT (t.canal = 'GAB' AND t.gab_id IS NULL)
          AND NOT (t.canal != 'GAB' AND t.gab_id IS NOT NULL)
    """,
    "digital_usage": """
        SELECT du.usage_id AS record_id, du.date_connexion AS date_ref
        FROM digital_usage du
        WHERE EXISTS (SELECT 1 FROM clients cl WHERE cl.client_id = du.client_id)
    """,
}


# ─────────────────────────────────────────────
# Logique de decision DIRECTE : regle x contexte x attribut (+ bruit)
# Retourne un array numpy de 'accepted'/'rejected'
# ─────────────────────────────────────────────
def decider(rule_id, contexte, df):
    n = len(df)
    attr = df["attr"].astype(float).values if "attr" in df.columns else np.zeros(n)

    if rule_id in ("TX_COMPTE_INEXISTANT", "COMPTE_CLIENT_INEXISTANT"):
        return np.array(["rejected"] * n)

    if rule_id == "DIGITAL_CLIENT_INEXISTANT":
        if contexte == "CAMPAGNE_CONTACT":
            return np.array(["rejected"] * n)
        if contexte == "ANALYSE_GEOGRAPHIQUE":
            return np.array(["accepted"] * n)
        anc = anciennete_annees(df["date_ref"]).values
        return bruiter_array(np.where(anc > 2.0, "rejected", "accepted"))

    if rule_id == "CONTACT_INVALIDE":
        if contexte == "CAMPAGNE_CONTACT":
            return np.array(["rejected"] * n)
        return np.array(["accepted"] * n)

    if rule_id == "CLIENT_AGENCE_FERMEE":
        if contexte in ("CAMPAGNE_CONTACT", "ANALYSE_TRANSACTIONNELLE"):
            return np.array(["accepted"] * n)
        anc = anciennete_annees(df["date_ref"]).values
        return bruiter_array(np.where(anc > 5.0, "rejected", "accepted"))

    if rule_id == "CARTE_ACTIVE_COMPTE_CLOTURE":
        if contexte in ("CAMPAGNE_CONTACT", "ANALYSE_GEOGRAPHIQUE"):
            return np.array(["accepted"] * n)
        annees = (jours_avant(df["date_ref"]) / 365.25).values  # coherent avec valeur_metier
        return bruiter_array(np.where(annees > 1.0, "rejected", "accepted"))

    if rule_id == "TX_GAB_SANS_ID":
        if contexte in ("CAMPAGNE_CONTACT", "ANALYSE_GEOGRAPHIQUE"):
            return np.array(["accepted"] * n)
        return bruiter_array(np.where(attr > 24000, "rejected", "accepted"))

    if rule_id == "TX_NON_GAB_AVEC_ID":
        if contexte in ("CAMPAGNE_CONTACT", "ANALYSE_GEOGRAPHIQUE"):
            return np.array(["accepted"] * n)
        return bruiter_array(np.where(attr > 24000, "rejected", "accepted"))

    return np.array(["accepted"] * n)


def valeur_metier_col(rule_id, df):
    """
    Colonne numerique valeur_metier : l'attribut qui declenche la zone de gris.
    - Regles a zone de gris : l'attribut pertinent (montant, anciennete, jours expir)
    - Regles dures, valides : 0 (pas d'attribut declencheur pertinent)
    Le modele combine rule_id + valeur_metier pour apprendre le seuil par regle.
    """
    n = len(df)

    # Regles utilisant le MONTANT
    if rule_id in ("TX_GAB_SANS_ID", "TX_NON_GAB_AVEC_ID"):
        return df["attr"].astype(float).round(2)

    # Regles utilisant l'ANCIENNETE (annees)
    if rule_id in ("CLIENT_AGENCE_FERMEE", "DIGITAL_CLIENT_INEXISTANT"):
        return anciennete_annees(df["date_ref"]).round(2)

    # Regle utilisant les JOURS AVANT EXPIRATION (en annees)
    if rule_id == "CARTE_ACTIVE_COMPTE_CLOTURE":
        return (jours_avant(df["date_ref"]) / 365.25).round(2)

    # Regles dures, CONTACT_INVALIDE, valides (AUCUNE) : pas de zone de gris -> 0
    return pd.Series([0.0] * n)


def date_id_col(df):
    """date_id au format AAAAMMJJ depuis date_ref."""
    d = pd.to_datetime(df["date_ref"], errors="coerce")
    return (d.dt.year * 10000 + d.dt.month * 100 + d.dt.day).fillna(0).astype(int)


def main():
    print("Generation du dataset ML — NIVEAU 2 (avec cascade par contexte)")
    print("=" * 65)
    engine = get_engine()

    # On stocke les decisions directes pour calculer la cascade ensuite.
    # Structure : anomalies[rule_id] = DataFrame(record_id, parent..., date_ref, attr)
    anomalies = {}
    parents_rejetes = {c: {"clients": set(), "comptes": set()} for c in CONTEXTES}

    blocs = []

    with engine.connect() as conn:
        # ── 1) DETECTION + DECISION DIRECTE (dans l'ordre parents d'abord) ──
        ordre = [
            "CONTACT_INVALIDE", "CLIENT_AGENCE_FERMEE",     # clients
            "COMPTE_CLIENT_INEXISTANT",                     # comptes
            "CARTE_ACTIVE_COMPTE_CLOTURE",                  # cartes
            "TX_COMPTE_INEXISTANT", "TX_GAB_SANS_ID", "TX_NON_GAB_AVEC_ID",  # tx
            "DIGITAL_CLIENT_INEXISTANT",                    # digital
        ]

        # dico pour retrouver le parent de chaque enfant (pour la cascade)
        # rempli via les colonnes parent_client / parent_compte des anomalies
        map_parent = {}  # (table, record_id) -> ('clients'/'comptes', parent_id)

        for rule_id in ordre:
            cfg = DETECTION[rule_id]
            df = pd.read_sql(text(cfg["sql"]), conn).reset_index(drop=True)
            table = cfg["table"]
            print(f"  {rule_id:30s} : {len(df):6d} anomalies")
            if len(df) == 0:
                continue

            vm = valeur_metier_col(rule_id, df)
            did = date_id_col(df)
            meta = META[rule_id]

            for contexte in CONTEXTES:
                dec = decider(rule_id, contexte, df)

                # enregistrer les parents rejetes (clients, comptes) pour la cascade
                if rule_id in ("CONTACT_INVALIDE", "CLIENT_AGENCE_FERMEE"):
                    rejected_ids = df["record_id"].values[dec == "rejected"]
                    parents_rejetes[contexte]["clients"].update(rejected_ids.tolist())
                if rule_id == "COMPTE_CLIENT_INEXISTANT":
                    rejected_ids = df["record_id"].values[dec == "rejected"]
                    parents_rejetes[contexte]["comptes"].update(rejected_ids.tolist())

                bloc = pd.DataFrame({
                    "table_origine":      table,
                    "record_id":          df["record_id"].astype(int).values,
                    "rule_id":            rule_id,
                    "dimension":          meta["dimension"],
                    "severity":           meta["severity"],
                    "label":              dec,
                    "decision_type":      "direct",
                    "is_valide":          "f",
                    "date_id":            did.values,
                    "dq_score":           DQ_SCORE[meta["severity"]],
                    "contexte_reporting": contexte,
                    "valeur_metier":      vm.values,
                })
                blocs.append(bloc)

        # ── 2) CASCADE : pour chaque contexte, rejeter les enfants des parents rejetes ──
        # On recupere les liens parent->enfant depuis la base.
        print("-" * 65)
        print("  Calcul de la cascade par contexte...")

        # enfants d'un client : comptes, transactions (via compte), cartes (via compte), digital
        comptes_par_client = pd.read_sql(text(
            "SELECT compte_id, client_id FROM comptes"), conn)
        tx_par_compte = pd.read_sql(text(
            "SELECT transaction_id, compte_id FROM transactions"), conn)
        cartes_par_compte = pd.read_sql(text(
            "SELECT carte_id, compte_id FROM cartes"), conn)
        digital_par_client = pd.read_sql(text(
            "SELECT usage_id, client_id FROM digital_usage"), conn)

        for contexte in CONTEXTES:
            cl_rej = parents_rejetes[contexte]["clients"]
            co_rej = set(parents_rejetes[contexte]["comptes"])

            # comptes des clients rejetes -> rejetes en cascade
            casc_comptes = comptes_par_client[comptes_par_client["client_id"].isin(cl_rej)]["compte_id"]
            co_rej.update(casc_comptes.tolist())

            # transactions des comptes rejetes
            casc_tx = tx_par_compte[tx_par_compte["compte_id"].isin(co_rej)]["transaction_id"]
            # cartes des comptes rejetes
            casc_cartes = cartes_par_compte[cartes_par_compte["compte_id"].isin(co_rej)]["carte_id"]
            # digital des clients rejetes
            casc_digital = digital_par_client[digital_par_client["client_id"].isin(cl_rej)]["usage_id"]

            cascade_sets = [
                ("comptes", casc_comptes, "COMPTE_CLIENT_INEXISTANT", "high"),
                ("transactions", casc_tx, "TX_COMPTE_INEXISTANT", "high"),
                ("cartes", casc_cartes, "CARTE_ACTIVE_COMPTE_CLOTURE", "high"),
                ("digital_usage", casc_digital, "DIGITAL_CLIENT_INEXISTANT", "high"),
            ]
            for table, ids, rule_id, sev in cascade_sets:
                ids = pd.Series(ids).astype(int).unique()
                if len(ids) == 0:
                    continue
                bloc = pd.DataFrame({
                    "table_origine":      table,
                    "record_id":          ids,
                    "rule_id":            rule_id,
                    "dimension":          "coherence",
                    "severity":           sev,
                    "label":              "rejected",
                    "decision_type":      "cascade",
                    "is_valide":          "f",
                    "date_id":            0,
                    "dq_score":           DQ_SCORE[sev],
                    "contexte_reporting": contexte,
                    "valeur_metier":      0.0,
                })
                blocs.append(bloc)
            print(f"    {contexte:26s} : cascade calculee")

        # ── 3) VALIDES (rule_id = AUCUNE) : toujours acceptes, dans les 3 contextes ──
        print("-" * 65)
        for table, sql in VALIDES.items():
            df = pd.read_sql(text(sql), conn).reset_index(drop=True)
            print(f"  VALIDES {table:22s} : {len(df):6d}")
            if len(df) == 0:
                continue
            did = date_id_col(df)
            vm = valeur_metier_col("AUCUNE", df)
            for contexte in CONTEXTES:
                bloc = pd.DataFrame({
                    "table_origine":      table,
                    "record_id":          df["record_id"].astype(int).values,
                    "rule_id":            "AUCUNE",
                    "dimension":          "aucune",
                    "severity":           "low",
                    "label":              "accepted",
                    "decision_type":      "valide",
                    "is_valide":          "t",
                    "date_id":            did.values,
                    "dq_score":           100,
                    "contexte_reporting": contexte,
                    "valeur_metier":      vm.values,
                })
                blocs.append(bloc)

    dataset = pd.concat(blocs, ignore_index=True)

    # ── DEDUPLICATION (fidele a l'ancien fct_quality : distinct on) ──
    # Un enregistrement peut apparaitre 2x dans un contexte : direct + cascade.
    # Priorite : direct > cascade > valide. On garde une seule ligne par
    # (table_origine, record_id, contexte_reporting).
    priorite = {"direct": 0, "cascade": 1, "valide": 2}
    dataset["_prio"] = dataset["decision_type"].map(priorite)
    dataset = (dataset
               .sort_values("_prio")
               .drop_duplicates(subset=["table_origine", "record_id", "contexte_reporting"],
                                keep="first")
               .drop(columns="_prio")
               .reset_index(drop=True))

    # reordonner les colonnes exactement comme l'ancien + les 2 nouvelles
    dataset = dataset[[
        "table_origine", "record_id", "rule_id", "dimension", "severity",
        "label", "decision_type", "is_valide", "date_id", "dq_score",
        "contexte_reporting", "valeur_metier"
    ]]

    os.makedirs("data/ml", exist_ok=True)
    dataset.to_csv(OUTPUT_PATH, index=False)

    print("=" * 65)
    print(f"Dataset ecrit : {OUTPUT_PATH}")
    print(f"Total lignes  : {len(dataset)}")
    print()
    print("Repartition des labels :")
    print(dataset["label"].value_counts())
    print((dataset["label"].value_counts(normalize=True) * 100).round(2))
    print()
    print("Repartition decision_type :")
    print(dataset["decision_type"].value_counts())
    print()
    print("Label par contexte :")
    print(pd.crosstab(dataset["contexte_reporting"], dataset["label"]))
    print()
    print("Termine.")


if __name__ == "__main__":
    main()