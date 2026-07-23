"""
Service de stockage objet (MinIO)
Al Barid Bank — Data Quality Platform

La zone d'atterrissage des donnees repose sur un stockage objet compatible S3.
Ce choix repond a la nature meme de l'ingestion : un fichier complet arrive, il
est lu une fois, puis archive. Ce mode d'acces — ecriture unique, lecture unique
— est celui pour lequel le stockage objet est concu, contrairement a un systeme
de fichiers dont l'arborescence, les verrous et les ecritures partielles ne sont
d'aucune utilite ici. C'est egalement le standard des plateformes de donnees,
ou les systemes sources deposent leurs fichiers via une interface reseau plutot
qu'en ecrivant dans un repertoire partage.

Trois compartiments structurent la chaine :

    landing/   les fichiers deposes par les systemes sources
    archive/   les fichiers traites avec succes (tracabilite)
    rejected/  les fichiers structurellement inexploitables, accompagnes
               du motif de leur rejet

Le deplacement d'un compartiment a l'autre garantit qu'un meme fichier ne peut
etre traite deux fois.
"""

import json
import os
from datetime import datetime

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "http://minio:9000")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")

BUCKET_LANDING  = "landing"
BUCKET_ARCHIVE  = "archive"
BUCKET_REJECTED = "rejected"


def client():
    """Client S3 pointant vers le stockage objet."""
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def lister(bucket: str = BUCKET_LANDING, suffixe: str = ".csv") -> list[str]:
    """Cles des objets presents dans un compartiment."""
    s3 = client()
    try:
        reponse = s3.list_objects_v2(Bucket=bucket)
    except ClientError as e:
        print(f"[STOCKAGE] Compartiment '{bucket}' inaccessible : {e}")
        return []

    objets = reponse.get("Contents", [])
    return sorted(
        o["Key"] for o in objets
        if o["Key"].lower().endswith(suffixe)
    )


def telecharger(cle: str, destination: str,
                bucket: str = BUCKET_LANDING) -> str:
    """
    Rapatrie un objet vers le systeme de fichiers local, en vue de son
    traitement. Le stockage objet est la zone d'atterrissage, non l'espace de
    travail : le fichier est donc telecharge avant d'etre exploite.
    """
    dossier = os.path.dirname(destination)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    client().download_file(bucket, cle, destination)
    return destination


def deposer(chemin_local: str, cle: str,
            bucket: str = BUCKET_LANDING) -> str:
    """Depose un fichier local dans un compartiment."""
    client().upload_file(chemin_local, bucket, cle)
    return cle


def deposer_contenu(contenu: str, cle: str, bucket: str) -> str:
    """Depose un contenu textuel comme objet (rapport de rejet, par exemple)."""
    client().put_object(
        Bucket=bucket,
        Key=cle,
        Body=contenu.encode("utf-8"),
        ContentType="application/json",
    )
    return cle


def deplacer(cle: str, bucket_source: str, bucket_cible: str,
             nouvelle_cle: str | None = None) -> str:
    """
    Deplace un objet d'un compartiment a l'autre. Le stockage objet ne connait
    pas le deplacement : l'operation consiste a copier puis a supprimer.
    """
    cible = nouvelle_cle or cle
    s3 = client()
    s3.copy_object(
        Bucket=bucket_cible,
        Key=cible,
        CopySource={"Bucket": bucket_source, "Key": cle},
    )
    s3.delete_object(Bucket=bucket_source, Key=cle)
    return cible


def archiver(cle: str) -> str:
    """Archive un fichier traite, horodate pour en preserver l'historique."""
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    return deplacer(cle, BUCKET_LANDING, BUCKET_ARCHIVE,
                    f"{horodatage}_{cle}")


def rejeter(cle: str, rapport: dict) -> str:
    """
    Ecarte un fichier inexploitable et conserve, a cote de lui, le motif du
    rejet. Un rejet est toujours explicable.
    """
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    cle_cible = f"{horodatage}_{cle}"

    deplacer(cle, BUCKET_LANDING, BUCKET_REJECTED, cle_cible)
    deposer_contenu(
        json.dumps(rapport, ensure_ascii=False, indent=2),
        cle_cible.replace(".csv", "_rapport.json"),
        BUCKET_REJECTED,
    )
    return cle_cible


def compter(bucket: str = BUCKET_LANDING) -> int:
    """Nombre d'objets CSV dans un compartiment."""
    return len(lister(bucket))
