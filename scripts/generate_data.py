"""
generate_data.py — Generation des donnees synthetiques Al Barid Bank
Anomalies injectees selon les regles metier retenues :
  - CONTACT_INVALIDE       : email invalide ET telephone NULL
  - CLIENT_AGENCE_FERMEE   : client rattache a une agence fermee
  - COMPTE_CLIENT_INEXISTANT
  - CARTE_ACTIVE_COMPTE_CLOTURE
  - TX_COMPTE_INEXISTANT
  - TX_GAB_SANS_ID
  - TX_NON_GAB_AVEC_ID
  - DIGITAL_CLIENT_INEXISTANT

Plus de CLIENT_ID_DUPLIQUE, CIN_DUPLIQUE, ni TX_OBSOLETE.
"""

import pandas as pd
import numpy as np
from faker import Faker
import random
import json
import os
from datetime import datetime, timedelta

fake = Faker('fr_FR')
np.random.seed(42)
random.seed(42)

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

report = {"generated_at": datetime.now().isoformat(), "datasets": {}}


def random_date(start, end):
    return start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))


def inject_pct(df, pct):
    n = max(1, int(len(df) * pct))
    return df.sample(n=n).index


# ─────────────────────────────────────────────
# 1. AGENCES — 3 fermees pour anomalie coherence
# ─────────────────────────────────────────────
def generate_agences():
    villes  = ["Casablanca", "Rabat", "Marrakech", "Fes", "Tanger",
               "Agadir", "Meknes", "Oujda", "Kenitra", "Tetouan"]
    regions = {
        "Casablanca": "Casablanca-Settat", "Rabat": "Rabat-Sale-Kenitra",
        "Marrakech": "Marrakech-Safi", "Fes": "Fes-Meknes",
        "Tanger": "Tanger-Tetouan-Al Hoceima", "Agadir": "Souss-Massa",
        "Meknes": "Fes-Meknes", "Oujda": "Oriental",
        "Kenitra": "Rabat-Sale-Kenitra", "Tetouan": "Tanger-Tetouan-Al Hoceima"
    }
    types = ["urbaine", "rurale", "premium"]
    rows  = []
    for i in range(1, 21):
        ville = random.choice(villes)
        d_ouv = random_date(datetime(2000, 1, 1), datetime(2018, 12, 31))
        if i <= 3:
            statut = "fermee"
            d_ferm = random_date(datetime(2019, 1, 1), datetime(2022, 12, 31))
        else:
            statut = "active"
            d_ferm = None
        rows.append({
            "agence_id":      i,
            "nom_agence":     f"Agence {ville} {i:02d}",
            "ville":          ville,
            "region":         regions[ville],
            "date_ouverture": d_ouv.date(),
            "type_agence":    random.choice(types),
            "statut":         statut,
            "date_fermeture": d_ferm.date() if d_ferm else None,
        })
    df = pd.DataFrame(rows)
    report["datasets"]["agences"] = {"total": len(df), "anomalies": {"agences_fermees": 3}}
    df.to_csv(f"{OUTPUT_DIR}/agences.csv", index=False)
    print(f"agences.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# 2. CLIENTS
# Anomalies :
#   - CONTACT_INVALIDE : email invalide ET telephone NULL (~3%) -> rejet
#   - email invalide SEUL avec telephone present (~3%) -> accepte
#   - telephone NULL SEUL avec email valide (~3%) -> accepte
#   - CLIENT_AGENCE_FERMEE (~2%) -> accepte avec transfert recommande
# ─────────────────────────────────────────────
def generate_clients(agences_df):
    active_ids = agences_df[agences_df["statut"] == "active"]["agence_id"].tolist()
    closed_ids = agences_df[agences_df["statut"] == "fermee"]["agence_id"].tolist()

    rows = []
    for i in range(1, 5001):
        rows.append({
            "client_id":      i,
            "cin":            fake.unique.bothify(text="??######").upper(),
            "nom":            fake.last_name(),
            "prenom":         fake.first_name(),
            "date_naissance": random_date(datetime(1955, 1, 1), datetime(2000, 12, 31)).date(),
            "telephone":      fake.numerify(text="06########"),
            "email":          fake.email(),
            "adresse":        fake.address().replace("\n", ", "),
            "agence_id":      random.choice(active_ids),
            "date_creation":  random_date(datetime(2015, 1, 1), datetime(2023, 12, 31)).date(),
        })
    df = pd.DataFrame(rows)
    counts = {}

    # CONTACT_INVALIDE : email invalide ET telephone NULL (~3%) -> sera rejete
    contact_idx = inject_pct(df, 0.03)
    df.loc[contact_idx, "telephone"] = None
    df.loc[contact_idx, "email"] = df.loc[contact_idx, "email"].apply(
        lambda e: e.replace("@", "").replace(".", "")
    )
    counts["contact_invalide"] = len(contact_idx)

    # Email invalide seul, telephone present (~3%) -> reste accepte (joignable par tel)
    remaining = df[~df.index.isin(contact_idx)]
    email_inv_idx = remaining.sample(frac=0.03, random_state=10).index
    df.loc[email_inv_idx, "email"] = df.loc[email_inv_idx, "email"].apply(
        lambda e: e.replace("@", "")
    )
    counts["email_invalide_seul_accepte"] = len(email_inv_idx)

    # Telephone NULL seul, email valide (~3%) -> reste accepte (joignable par email)
    remaining2 = df[~df.index.isin(contact_idx) & ~df.index.isin(email_inv_idx)]
    tel_null_idx = remaining2.sample(frac=0.03, random_state=11).index
    df.loc[tel_null_idx, "telephone"] = None
    counts["telephone_null_seul_accepte"] = len(tel_null_idx)

    # CLIENT_AGENCE_FERMEE (~2%)
    closed_idx = inject_pct(df, 0.02)
    df.loc[closed_idx, "agence_id"] = random.choice(closed_ids)
    counts["agence_fermee"] = len(closed_idx)

    report["datasets"]["clients"] = {"total": len(df), "anomalies": counts}
    df.to_csv(f"{OUTPUT_DIR}/clients.csv", index=False)
    print(f"clients.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# 3. COMPTES
# Anomalie : COMPTE_CLIENT_INEXISTANT (~3%)
# ─────────────────────────────────────────────
def generate_comptes(clients_df):
    valid_ids = clients_df["client_id"].tolist()
    types     = ["courant", "epargne", "professionnel"]
    statuts   = ["actif", "cloture", "suspendu"]
    rows = []
    for i in range(1, 7001):
        rows.append({
            "compte_id":      i,
            "client_id":      random.choice(valid_ids),
            "type_compte":    random.choice(types),
            "date_ouverture": random_date(datetime(2015, 1, 1), datetime(2023, 12, 31)).date(),
            "solde":          round(random.uniform(0, 500000), 2),
            "statut":         random.choices(statuts, weights=[75, 15, 10])[0],
        })
    df = pd.DataFrame(rows)
    counts = {}

    # COMPTE_CLIENT_INEXISTANT (~3%)
    ghost_idx = inject_pct(df, 0.03)
    df.loc[ghost_idx, "client_id"] = random.randint(90000, 99999)
    counts["client_inexistant"] = len(ghost_idx)

    report["datasets"]["comptes"] = {"total": len(df), "anomalies": counts}
    df.to_csv(f"{OUTPUT_DIR}/comptes.csv", index=False)
    print(f"comptes.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# 4. CARTES
# Anomalie : CARTE_ACTIVE_COMPTE_CLOTURE (~3%)
# ─────────────────────────────────────────────
def generate_cartes(comptes_df):
    clotures    = comptes_df[comptes_df["statut"] == "cloture"]["compte_id"].tolist()
    actifs      = comptes_df[comptes_df["statut"] == "actif"]["compte_id"].tolist()
    types_carte = ["Visa", "Mastercard", "CIB"]
    statuts     = ["active", "expiree", "bloquee"]
    rows = []
    for i in range(1, 6501):
        rows.append({
            "carte_id":        i,
            "compte_id":       random.choice(actifs),
            "type_carte":      random.choice(types_carte),
            "date_expiration": random_date(datetime(2024, 1, 1), datetime(2028, 12, 31)).date(),
            "statut":          random.choices(statuts, weights=[70, 20, 10])[0],
        })
    df = pd.DataFrame(rows)
    counts = {}

    # CARTE_ACTIVE_COMPTE_CLOTURE (~3%)
    if clotures:
        active_idx = df[df["statut"] == "active"].sample(frac=0.03, random_state=5).index
        df.loc[active_idx, "compte_id"] = random.choice(clotures)
        counts["carte_active_compte_cloture"] = len(active_idx)

    report["datasets"]["cartes"] = {"total": len(df), "anomalies": counts}
    df.to_csv(f"{OUTPUT_DIR}/cartes.csv", index=False)
    print(f"cartes.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# 5. GABS
# ─────────────────────────────────────────────
def generate_gabs(agences_df):
    active_ag   = agences_df[agences_df["statut"] == "active"]
    types_gab   = ["distributeur", "depot", "mixte"]
    statuts_gab = ["operationnel", "en panne", "hors service"]
    rows = []
    for i in range(1, 101):
        ag = active_ag.sample(1).iloc[0]
        rows.append({
            "gab_id":    i,
            "agence_id": ag["agence_id"],
            "type_gab":  random.choice(types_gab),
            "ville":     ag["ville"],
            "statut":    random.choices(statuts_gab, weights=[80, 12, 8])[0],
        })
    df = pd.DataFrame(rows)
    report["datasets"]["gabs"] = {"total": len(df), "anomalies": {}}
    df.to_csv(f"{OUTPUT_DIR}/gabs.csv", index=False)
    print(f"gabs.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# 6. TRANSACTIONS
# Anomalies :
#   - TX_COMPTE_INEXISTANT (~3%)
#   - TX_GAB_SANS_ID (~2%)
#   - TX_NON_GAB_AVEC_ID (~2%)
# ─────────────────────────────────────────────
def generate_transactions(comptes_df, gabs_df):
    valid_comptes = comptes_df["compte_id"].tolist()
    valid_gabs    = gabs_df["gab_id"].tolist()
    types_tx      = ["retrait", "versement", "virement", "paiement"]
    canaux        = ["agence", "GAB", "BBM", "BaridNet"]
    rows = []
    for i in range(1, 100001):
        canal = random.choice(canaux)
        rows.append({
            "transaction_id":   i,
            "compte_id":        random.choice(valid_comptes),
            "date_transaction": random_date(datetime(2020, 1, 1), datetime(2024, 12, 31)),
            "montant":          round(random.uniform(10, 50000), 2),
            "type_transaction": random.choice(types_tx),
            "canal":            canal,
            "agence_id":        random.randint(4, 20) if canal == "agence" else None,
            "gab_id":           random.choice(valid_gabs) if canal == "GAB" else None,
        })
    df = pd.DataFrame(rows)
    counts = {}

    # TX_COMPTE_INEXISTANT (~3%)
    ghost_idx = inject_pct(df, 0.03)
    df.loc[ghost_idx, "compte_id"] = random.randint(90000, 99999)
    counts["compte_inexistant"] = len(ghost_idx)

    # TX_GAB_SANS_ID (~2%)
    gab_tx_idx = df[df["canal"] == "GAB"].sample(frac=0.02, random_state=6).index
    df.loc[gab_tx_idx, "gab_id"] = None
    counts["gab_sans_id"] = len(gab_tx_idx)

    # TX_NON_GAB_AVEC_ID (~2%)
    non_gab_idx = df[df["canal"] != "GAB"].sample(frac=0.02, random_state=7).index
    df.loc[non_gab_idx, "gab_id"] = random.choice(valid_gabs)
    counts["non_gab_avec_id"] = len(non_gab_idx)

    report["datasets"]["transactions"] = {"total": len(df), "anomalies": counts}
    df.to_csv(f"{OUTPUT_DIR}/transactions.csv", index=False)
    print(f"transactions.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# 7. DIGITAL USAGE
# Anomalie : DIGITAL_CLIENT_INEXISTANT (~2%)
# ─────────────────────────────────────────────
def generate_digital_usage(clients_df):
    valid_ids = clients_df["client_id"].tolist()
    canaux    = ["BBM", "BaridNet"]
    actions   = ["consultation", "virement", "paiement facture", "telechargement releve"]
    rows = []
    for i in range(1, 50001):
        rows.append({
            "usage_id":       i,
            "client_id":      random.choice(valid_ids),
            "date_connexion": random_date(datetime(2020, 1, 1), datetime(2024, 12, 31)),
            "canal":          random.choice(canaux),
            "action":         random.choice(actions),
        })
    df = pd.DataFrame(rows)
    counts = {}

    # DIGITAL_CLIENT_INEXISTANT (~2%)
    ghost_idx = inject_pct(df, 0.02)
    df.loc[ghost_idx, "client_id"] = random.randint(90000, 99999)
    counts["client_inexistant"] = len(ghost_idx)

    report["datasets"]["digital_usage"] = {"total": len(df), "anomalies": counts}
    df.to_csv(f"{OUTPUT_DIR}/digital_usage.csv", index=False)
    print(f"digital_usage.csv : {len(df)} lignes")
    return df


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Generation des donnees synthetiques — Al Barid Bank\n")
    agences_df      = generate_agences()
    clients_df      = generate_clients(agences_df)
    comptes_df      = generate_comptes(clients_df)
    cartes_df       = generate_cartes(comptes_df)
    gabs_df         = generate_gabs(agences_df)
    transactions_df = generate_transactions(comptes_df, gabs_df)
    digital_df      = generate_digital_usage(clients_df)

    with open(f"{OUTPUT_DIR}/anomalies_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nResume des anomalies injectees :")
    for ds, info in report["datasets"].items():
        print(f"  {ds}: {info['total']} lignes | anomalies: {info['anomalies']}")
    print("\nPhase 1 terminee.")