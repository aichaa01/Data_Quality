"""
DAG 1 — Ingestion des donnees
Al Barid Bank — Data Quality Platform

Declencheur : le depot d'un fichier CSV dans le compartiment « landing » du
              stockage objet declenche ce DAG de maniere EVENEMENTIELLE. MinIO
              emet une notification, relayee a Airflow par le service pont. Le
              pipeline demarre donc des qu'un fichier arrive, sans surveillance
              active ni delai.

Chaine :

    Capteur (compartiment landing)
        v
    Validation structurelle   -> fichiers inexploitables ecartes (rejected/)
        v
    Chargement en base        -> donnees brutes, sans controle d'integrite
        v
    Transformation dbt        -> preparation, detection, tests de qualite
        v
    Archivage                 -> tracabilite des fichiers traites

DEUX NIVEAUX DE CONTROLE, A NE PAS CONFONDRE :

  * La VALIDATION STRUCTURELLE, en amont, ecarte les fichiers inexploitables :
    illisibles, vides, depourvus des colonnes attendues. C'est un rejet
    TECHNIQUE.

  * Les REGLES METIER, en aval (dbt), detectent les anomalies de qualite.
    Un fichier rempli d'anomalies est parfaitement NORMAL — c'est l'objet meme
    de la plateforme. Ces anomalies deviennent des decisions en attente dans
    l'application.

Un fichier n'est donc jamais ecarte parce qu'il contient des anomalies.

PRINCIPE DIRECTEUR : la chaine ne decide jamais a la place du reporter. Elle
prepare la decision, elle ne s'y substitue pas.
"""

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/project"
WORK_DIR    = f"{PROJECT_DIR}/data/processing"   # espace de travail local

default_args = {
    "owner": "data-quality",
    "retries": 0,   # pas de retry : le fichier est deja archive apres traitement,
                    # un nouvel essai retomberait sur un compartiment vide.
    "depends_on_past": False,
}


# ─────────────────────────────────────────────────────────────
# Etapes
# ─────────────────────────────────────────────────────────────

def valider_et_rapatrier(**context):
    """
    Telecharge chaque objet du compartiment d'atterrissage, le valide, puis
    l'oriente : les fichiers exploitables sont conserves dans l'espace de
    travail, les autres sont ecartes vers le compartiment de rejet, accompagnes
    du motif.

    Rappel : seule l'inexploitabilite structurelle motive un rejet. La presence
    d'anomalies metier, elle, est attendue.
    """
    sys.path.insert(0, PROJECT_DIR)
    from scripts import storage
    from scripts.validate_files import valider

    os.makedirs(WORK_DIR, exist_ok=True)

    cles = storage.lister(storage.BUCKET_LANDING)
    if not cles:
        # Compartiment vide : ce n'est pas une erreur. Cela survient lorsqu'une
        # execution est relancee apres qu'un precedent essai a deja traite et
        # archive le fichier, ou en cas de double notification. On termine
        # proprement plutot que d'echouer.
        from airflow.exceptions import AirflowSkipException
        raise AirflowSkipException("Compartiment d'atterrissage vide : rien a traiter.")

    print(f"{len(cles)} objet(s) dans le compartiment d'atterrissage.")
    print("=" * 62)

    acceptes, rejetes = [], []

    for cle in cles:
        local = os.path.join(WORK_DIR, os.path.basename(cle))
        storage.telecharger(cle, local, storage.BUCKET_LANDING)

        rapport = valider(local)

        if rapport["valide"]:
            acceptes.append({"cle": cle, "local": local, **rapport})
            avert = ""
            if rapport["avertissements"]:
                avert = "  [!] " + " ; ".join(rapport["avertissements"])
            print(f"  ACCEPTE  {cle:32s} {rapport['entite']:14s} "
                  f"{rapport['lignes']:>7d} lignes{avert}")
        else:
            storage.rejeter(cle, rapport)
            if os.path.exists(local):
                os.remove(local)
            rejetes.append(rapport)
            print(f"  ECARTE   {cle:32s} {' ; '.join(rapport['erreurs'])}")

    print("=" * 62)
    print(f"Retenus : {len(acceptes)}  |  Ecartes : {len(rejetes)}")

    if not acceptes:
        raise ValueError("Aucun fichier exploitable : la chaine s'interrompt.")

    context["ti"].xcom_push(key="acceptes", value=acceptes)
    context["ti"].xcom_push(key="nb_rejetes", value=len(rejetes))
    return len(acceptes)


def charger_donnees(**context):
    """
    Charge les fichiers retenus dans la base relationnelle (etat courant) :

      * clients, comptes, cartes (etat evolutif) -> UPSERT. La nouvelle version
        ecrase l'ancienne. La base ne conserve que l'etat courant ; l'historique
        sera capture dans l'entrepot par le snapshot dbt (etape suivante).

      * transactions, digital_usage (evenements immuables) -> AJOUT simple.

    Un enregistrement mis a jour repasse par la detection au prochain cycle dbt,
    comme un nouvel enregistrement. Les decisions prises sur ses versions
    anterieures sont conservees.
    """
    sys.path.insert(0, PROJECT_DIR)
    from scripts.loading import get_engine, charger_fichier

    acceptes = context["ti"].xcom_pull(key="acceptes",
                                       task_ids="valider_et_rapatrier")

    engine = get_engine()
    total = 0
    details = []

    for f in acceptes:
        resultat = charger_fichier(engine, f["entite"], f["local"])
        total += resultat["lignes"]
        details.append(resultat)

    print(f"Total traite : {total} lignes")
    context["ti"].xcom_push(key="lignes", value=total)
    context["ti"].xcom_push(key="details", value=details)
    return total


def archiver(**context):
    """
    Archive les fichiers traites et nettoie l'espace de travail. Le passage du
    compartiment d'atterrissage a celui d'archive garantit qu'un meme fichier
    ne sera pas traite deux fois, tout en preservant sa tracabilite.
    """
    sys.path.insert(0, PROJECT_DIR)
    from scripts import storage

    acceptes = context["ti"].xcom_pull(key="acceptes",
                                       task_ids="valider_et_rapatrier")

    for f in acceptes:
        storage.archiver(f["cle"])
        if os.path.exists(f["local"]):
            os.remove(f["local"])
        print(f"  archive : {f['cle']}")

    print(f"{len(acceptes)} fichier(s) archive(s).")
    return len(acceptes)


def rapport_final(**context):
    """Synthese de l'execution."""
    ti = context["ti"]
    acceptes = ti.xcom_pull(key="acceptes",   task_ids="valider_et_rapatrier") or []
    rejetes  = ti.xcom_pull(key="nb_rejetes", task_ids="valider_et_rapatrier") or 0
    lignes   = ti.xcom_pull(key="lignes",     task_ids="charger_donnees") or 0

    print("=" * 62)
    print("INGESTION TERMINEE")
    print("=" * 62)
    print(f"  Fichiers integres : {len(acceptes)}")
    print(f"  Fichiers ecartes  : {rejetes}")
    print(f"  Lignes chargees   : {lignes}")
    print()
    print("Les anomalies detectees se presentent desormais dans l'application")
    print("comme des decisions en attente. La chaine prepare la decision,")
    print("elle ne se substitue pas au reporter.")
    print("=" * 62)


# ─────────────────────────────────────────────────────────────
# DAG
# ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="ingestion_donnees",
    description="Ingestion evenementielle (declenchee par MinIO) : "
                "validation, chargement, detection des anomalies",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,          # declenche par le depot d'un fichier
    catchup=False,
    max_active_runs=1,      # une seule ingestion a la fois
    tags=["ingestion", "qualite", "minio"],
) as dag:

    valider_task = PythonOperator(
        task_id="valider_et_rapatrier",
        python_callable=valider_et_rapatrier,
        doc_md="Validation structurelle. Un fichier n'est ecarte que s'il est "
               "inexploitable, jamais parce qu'il contient des anomalies.",
    )

    charger = PythonOperator(
        task_id="charger_donnees",
        python_callable=charger_donnees,
        doc_md="Chargement en base sans contrainte d'integrite, afin que les "
               "incoherences puissent etre detectees plutot qu'ecartees.",
    )

    transformer = BashOperator(
        task_id="transformer_dbt",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt && "
            "dbt run --profiles-dir . --target dev && "
            "dbt test --profiles-dir . --target dev || true"
        ),
        doc_md="Preparation, detection des anomalies et tests de qualite. "
               "Les echecs de tests sont ATTENDUS : ils correspondent aux "
               "anomalies detectees, non a une defaillance de la chaine.",
    )

    archiver_task = PythonOperator(
        task_id="archiver",
        python_callable=archiver,
        doc_md="Archivage des fichiers traites : tracabilite et garantie "
               "qu'un fichier ne sera pas traite deux fois.",
    )

    rapport = PythonOperator(
        task_id="rapport",
        python_callable=rapport_final,
    )

    valider_task >> charger >> transformer >> archiver_task >> rapport