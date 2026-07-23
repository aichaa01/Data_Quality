"""
Service pont — MinIO vers Airflow
Al Barid Bank — Data Quality Platform

MinIO emet une notification lorsqu'un objet est depose dans le compartiment
d'atterrissage. Cette notification ne peut declencher Airflow directement : son
format differe de celui qu'attend l'API d'Airflow. Ce service fait le lien.

    MinIO (depot d'un fichier)
        v   notification (webhook)
    Ce service pont
        v   appel de l'API REST
    Airflow (declenchement du DAG d'ingestion)

Le service se limite a ce role de traduction : il recoit l'evenement MinIO,
verifie qu'il s'agit bien d'un depot de fichier CSV, puis demande a Airflow de
declencher une execution du DAG d'ingestion.
"""

import os
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI, Request

app = FastAPI(title="Pont MinIO-Airflow")

# Configuration (injectee par docker-compose)
AIRFLOW_API   = os.getenv("AIRFLOW_API", "http://airflow-webserver:8080/api/v1")
AIRFLOW_USER  = os.getenv("AIRFLOW_USER", "admin")
AIRFLOW_PASS  = os.getenv("AIRFLOW_PASS", "admin")
DAG_ID        = os.getenv("DAG_ID", "ingestion_donnees")


@app.get("/")
def sante():
    """Verification de disponibilite."""
    return {"service": "pont-minio-airflow", "cible": DAG_ID, "statut": "actif"}


@app.post("/minio-event")
async def minio_event(request: Request):
    """
    Recoit une notification MinIO et declenche le DAG d'ingestion.

    MinIO envoie un evenement decrivant l'objet depose. On ne retient que les
    depots (evenements « ObjectCreated ») portant sur un fichier CSV, afin de
    ne pas declencher inutilement le pipeline.
    """
    try:
        evenement = await request.json()
    except Exception:
        return {"declenche": False, "raison": "corps illisible"}

    # MinIO structure l'evenement sous 'Records'
    records = evenement.get("Records", [])
    if not records:
        return {"declenche": False, "raison": "aucun enregistrement"}

    # Verifier qu'au moins un objet CSV a ete depose
    csv_depose = False
    for rec in records:
        nom_evenement = rec.get("eventName", "")
        cle = rec.get("s3", {}).get("object", {}).get("key", "")
        if "ObjectCreated" in nom_evenement and cle.lower().endswith(".csv"):
            csv_depose = True
            print(f"[PONT] Depot detecte : {cle}")

    if not csv_depose:
        return {"declenche": False, "raison": "pas de fichier CSV"}

    # Declencher le DAG via l'API REST d'Airflow
    run_id = f"minio_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            reponse = await client.post(
                f"{AIRFLOW_API}/dags/{DAG_ID}/dagRuns",
                auth=(AIRFLOW_USER, AIRFLOW_PASS),
                json={
                    "dag_run_id": run_id,
                    "conf": {"origine": "minio", "evenement": "depot_fichier"},
                },
            )
        except Exception as e:
            print(f"[PONT] Airflow injoignable : {e}")
            return {"declenche": False, "raison": f"Airflow injoignable : {e}"}

    if reponse.status_code in (200, 409):
        # 200 : declenche ; 409 : une execution est deja en cours (max_active_runs)
        etat = "declenche" if reponse.status_code == 200 else "deja en cours"
        print(f"[PONT] DAG {DAG_ID} : {etat}")
        return {"declenche": True, "run_id": run_id, "etat": etat}

    print(f"[PONT] Echec API Airflow ({reponse.status_code}) : {reponse.text}")
    return {"declenche": False, "raison": f"API Airflow : {reponse.status_code}"}
