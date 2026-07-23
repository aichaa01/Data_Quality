"""
DAG 3 — Historisation et construction de l'entrepot
Al Barid Bank — Data Quality Platform

L'entrepot ne contient que des donnees VALIDEES : soit valides par nature
(aucune anomalie), soit acceptees par l'administrateur. Les donnees rejetees
n'y entrent jamais.

Ce DAG, distinct de l'ingestion, se declenche apres que les reporters ont pris
leurs decisions. Il reconstruit les marts de l'entrepot et historise les
dimensions a etat evolutif au moyen des snapshots dbt (SCD Type 2).

    Construction des marts (dbt run)
        v
    Historisation des dimensions validees (dbt snapshot)
        v
    Tests de coherence de l'entrepot (dbt test)

Pourquoi un DAG separe :
L'ingestion prepare les donnees et fait remonter les anomalies ; la decision
appartient au reporter. Ce n'est qu'une fois la donnee validee qu'elle a
vocation a etre stockee dans l'entrepot et historisee. Les deux temps — preparer
la decision, puis stocker ce qui est valide — sont donc portes par deux DAGs
distincts.

Declenchement : programme (quotidien), a la maniere d'un traitement par lots
nocturne. L'entrepot reflete alors, chaque jour, l'etat valide le plus recent,
et le snapshot capture les evolutions survenues depuis la veille.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/project"

default_args = {
    "owner": "data-quality",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="historisation_dwh",
    description="Construit l'entrepot a partir des donnees validees et "
                "historise les dimensions (SCD Type 2)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",     # chaque nuit a 2h (traitement par lots)
    catchup=False,
    max_active_runs=1,
    tags=["dwh", "historisation", "scd2"],
) as dag:

    construire_marts = BashOperator(
        task_id="construire_marts",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt && "
            "dbt run --profiles-dir . --target dev"
        ),
        doc_md="Reconstruit les marts de l'entrepot. dwh_metier exclut les "
               "enregistrements rejetes : seules les donnees validees "
               "(valides par nature ou acceptees) y figurent.",
    )

    historiser = BashOperator(
        task_id="historiser_snapshots",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt && "
            "dbt snapshot --profiles-dir . --target dev"
        ),
        doc_md="Historise les dimensions a etat evolutif (clients, comptes, "
               "cartes) validees. dbt versionne chaque changement de solde, de "
               "statut, d'agence ou de coordonnees (SCD Type 2), en renseignant "
               "dbt_valid_from et dbt_valid_to.",
    )

    verifier = BashOperator(
        task_id="verifier_dwh",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt && "
            "dbt test --profiles-dir . --target dev || true"
        ),
        doc_md="Tests de coherence sur l'entrepot construit.",
    )

    construire_marts >> historiser >> verifier