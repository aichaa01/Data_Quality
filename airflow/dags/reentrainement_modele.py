"""
DAG 2 — Reentrainement du modele
Al Barid Bank — Data Quality Platform

Le modele est entraine sur un jeu de donnees synthetique. En exploitation, les
reporters prennent des decisions reelles, qui s'accumulent. Ces decisions
constituent un signal precieux, notamment lorsqu'elles portent sur des
contextes de reporting inconnus du modele.

DECLENCHEURS (le reentrainement est lance si l'une des conditions est remplie) :

  1. VOLUME    : au moins 20 000 nouvelles decisions depuis le dernier
                 entrainement. Condition d'hygiene : elle evite de reentrainer
                 sur un signal negligeable au regard du jeu initial.

  2. NOUVEAUTE : au moins 500 decisions dans un contexte sur lequel le modele
                 n'a jamais ete entraine. C'est cette condition qui permet
                 reellement au systeme de progresser : sur un contexte inconnu,
                 le modele ne dispose d'aucune information, et quelques
                 centaines de decisions lui en apportent une.

DONNEES D'ENTRAINEMENT :
Le modele est reentraine sur le jeu synthetique initial ENRICHI des decisions
reelles accumulees.

  Reserve methodologique : le jeu synthetique procede des regles definies par
  la conception, tandis que les decisions reelles procedent du jugement des
  reporters. Les melanger revient a apprendre une logique hybride. Ce choix est
  assume : il preserve une base d'apprentissage large tout en integrant le
  signal reel, seul porteur des contextes nouveaux.

Le modele n'est remplace que s'il ameliore effectivement la performance.
"""

import os
import shutil
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator

PROJECT_DIR = "/opt/project"
MODEL_DIR   = f"{PROJECT_DIR}/app/models"
ML_DIR      = f"{PROJECT_DIR}/data/ml"

SEUIL_VOLUME    = 20_000   # nouvelles decisions depuis le dernier entrainement
SEUIL_NOUVEAUTE = 500      # decisions dans un contexte inconnu du modele

default_args = {
    "owner": "data-quality",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _engine():
    from sqlalchemy import create_engine
    url = (f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:"
           f"{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:"
           f"{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}")
    return create_engine(url)


# ─────────────────────────────────────────────────────────────
# 1. Evaluation des declencheurs
# ─────────────────────────────────────────────────────────────

def evaluer_declencheurs(**context):
    """Determine s'il y a lieu de reentrainer, et pour quel motif."""
    import joblib
    import pandas as pd
    from sqlalchemy import text

    engine = _engine()

    # Contextes sur lesquels le modele a ete entraine
    try:
        colonnes = joblib.load(f"{MODEL_DIR}/colonnes_modele.pkl")
        prefixe = "contexte_reporting_"
        contextes_connus = {c[len(prefixe):] for c in colonnes
                            if c.startswith(prefixe)}
    except Exception as e:
        print(f"Modele illisible ({e}) : reentrainement necessaire.")
        context["ti"].xcom_push(key="motif", value="modele_absent")
        return True

    print(f"Contextes connus du modele : {sorted(contextes_connus)}")

    with engine.connect() as conn:
        # Date du dernier entrainement
        derniere = conn.execute(text("""
            SELECT MAX(trained_at) FROM model_training_runs WHERE success = TRUE
        """)).scalar()

        # Condition 1 — volume de nouvelles decisions
        if derniere:
            volume = conn.execute(text("""
                SELECT COUNT(*) FROM admin_decisions WHERE decided_at > :d
            """), {"d": derniere}).scalar()
        else:
            volume = conn.execute(text(
                "SELECT COUNT(*) FROM admin_decisions")).scalar()

        # Condition 2 — decisions dans des contextes inconnus
        nouveautes = conn.execute(text("""
            SELECT contexte_reporting, COUNT(*) AS n
            FROM model_predictions
            WHERE decision_reporter IS NOT NULL
            GROUP BY contexte_reporting
        """)).fetchall()

    print(f"Nouvelles decisions depuis le dernier entrainement : {volume}")

    contextes_nouveaux = {
        ctx: n for ctx, n in nouveautes
        if ctx not in contextes_connus and n >= SEUIL_NOUVEAUTE
    }
    if contextes_nouveaux:
        print(f"Contextes nouveaux suffisamment documentes : {contextes_nouveaux}")

    # Decision
    if contextes_nouveaux:
        motif = f"nouveaute ({', '.join(contextes_nouveaux)})"
    elif volume >= SEUIL_VOLUME:
        motif = f"volume ({volume} nouvelles decisions)"
    else:
        print(f"Aucun declencheur : volume {volume}/{SEUIL_VOLUME}, "
              f"aucun contexte nouveau atteignant {SEUIL_NOUVEAUTE} decisions.")
        context["ti"].xcom_push(key="motif", value=None)
        return False

    print(f"Reentrainement declenche — motif : {motif}")
    context["ti"].xcom_push(key="motif", value=motif)
    context["ti"].xcom_push(key="volume", value=volume)
    return True


def brancher(**context):
    """Oriente la suite selon le resultat de l'evaluation."""
    doit = context["ti"].xcom_pull(task_ids="evaluer_declencheurs")
    return "construire_jeu_entrainement" if doit else "aucun_reentrainement"


# ─────────────────────────────────────────────────────────────
# 2. Construction du jeu d'entrainement
# ─────────────────────────────────────────────────────────────

def construire_jeu_entrainement(**context):
    """
    Jeu synthetique initial + decisions reelles accumulees (option A).
    Les decisions reelles sont mises au format du jeu d'entrainement.
    """
    import pandas as pd
    from sqlalchemy import text

    engine = _engine()

    # Base synthetique
    chemin_synthetique = f"{ML_DIR}/ml_dataset_v2.csv"
    if not os.path.exists(chemin_synthetique):
        raise FileNotFoundError(f"Jeu synthetique introuvable : {chemin_synthetique}")

    base = pd.read_csv(chemin_synthetique)
    print(f"Jeu synthetique : {len(base)} lignes")

    # Decisions reelles, tracees lors des predictions
    with engine.connect() as conn:
        reelles = pd.read_sql(text("""
            SELECT table_origine, record_id, rule_id, contexte_reporting,
                   valeur_metier, decision_reporter AS label
            FROM model_predictions
            WHERE decision_reporter IS NOT NULL
        """), conn)

    print(f"Decisions reelles : {len(reelles)} lignes")

    if len(reelles) > 0:
        # Alignement sur le schema du jeu synthetique
        for colonne in base.columns:
            if colonne not in reelles.columns:
                reelles[colonne] = None
        reelles = reelles[base.columns]

        jeu = pd.concat([base, reelles], ignore_index=True)

        # Une decision reelle prime sur la donnee synthetique correspondante
        jeu = jeu.drop_duplicates(
            subset=["table_origine", "record_id", "contexte_reporting"],
            keep="last",
        )
    else:
        jeu = base

    chemin = f"{ML_DIR}/training_dataset.csv"
    jeu.to_csv(chemin, index=False)

    print(f"Jeu d'entrainement : {len(jeu)} lignes -> {chemin}")
    context["ti"].xcom_push(key="lignes", value=len(jeu))
    return chemin


# ─────────────────────────────────────────────────────────────
# 3. Entrainement
# ─────────────────────────────────────────────────────────────

def entrainer(**context):
    """
    Entraine une foret aleatoire, modele retenu a l'issue de la comparaison
    initiale pour sa capacite a modeliser les seuils des zones de gris.
    Le decoupage est stratifie, en raison du fort desequilibre des classes.
    """
    import joblib
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score, precision_score, recall_score

    jeu = pd.read_csv(f"{ML_DIR}/training_dataset.csv")

    # Variables retenues : les seules disponibles au moment de la prediction,
    # exemptes de fuite et de redondance.
    FEATURES = ["table_origine", "rule_id", "contexte_reporting", "valeur_metier"]

    X = jeu[FEATURES].copy()
    X["valeur_metier"] = pd.to_numeric(X["valeur_metier"], errors="coerce").fillna(0)
    y = jeu["label"].map({"accepted": 0, "rejected": 1})

    X = pd.get_dummies(
        X, columns=["table_origine", "rule_id", "contexte_reporting"]
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    modele = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",   # correction du desequilibre
        random_state=42,
        n_jobs=-1,
    )
    modele.fit(X_train, y_train)

    y_pred = modele.predict(X_test)
    metriques = {
        "f1":        round(float(f1_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred)), 4),
        "rappel":    round(float(recall_score(y_test, y_pred)), 4),
    }

    print(f"F1 : {metriques['f1']}  |  Precision : {metriques['precision']}  "
          f"|  Rappel : {metriques['rappel']}")

    # Le modele est mis de cote : il ne remplacera l'actuel que s'il fait mieux.
    joblib.dump(modele,        f"{ML_DIR}/modele_candidat.pkl")
    joblib.dump(list(X.columns), f"{ML_DIR}/colonnes_candidat.pkl")

    context["ti"].xcom_push(key="metriques", value=metriques)
    context["ti"].xcom_push(key="n_features", value=len(X.columns))
    return metriques


# ─────────────────────────────────────────────────────────────
# 4. Deploiement conditionnel
# ─────────────────────────────────────────────────────────────

def deployer_si_meilleur(**context):
    """
    Le modele candidat ne remplace le modele en service que s'il l'ameliore.
    Un reentrainement ne garantit pas un progres : il peut degrader la
    performance. Cette verification protege l'exploitation.

    Une tolerance est admise lorsque le reentrainement est motive par
    l'apparition d'un contexte nouveau : le modele candidat couvre alors un
    perimetre plus large, ce qui peut se traduire par une legere baisse du F1
    global tout en constituant un progres reel.
    """
    import joblib
    import pandas as pd
    from sqlalchemy import text
    from sklearn.metrics import f1_score

    ti = context["ti"]
    metriques = ti.xcom_pull(key="metriques", task_ids="entrainer")
    motif     = ti.xcom_pull(key="motif",     task_ids="evaluer_declencheurs")
    lignes    = ti.xcom_pull(key="lignes",    task_ids="construire_jeu_entrainement")

    engine = _engine()

    # Performance du modele actuellement en service
    with engine.connect() as conn:
        f1_actuel = conn.execute(text("""
            SELECT f1 FROM model_training_runs
            WHERE success = TRUE
            ORDER BY trained_at DESC LIMIT 1
        """)).scalar()

    f1_candidat = metriques["f1"]
    nouveau_contexte = motif is not None and motif.startswith("nouveaute")

    # Sans historique, le candidat est deploye.
    if f1_actuel is None:
        deployer = True
        raison = "aucun modele de reference"
    elif f1_candidat >= float(f1_actuel):
        deployer = True
        raison = f"F1 {f1_candidat} >= {f1_actuel}"
    elif nouveau_contexte and f1_candidat >= float(f1_actuel) - 0.02:
        # Tolerance : le perimetre s'elargit a un contexte jusque-la inconnu.
        deployer = True
        raison = (f"contexte nouveau couvert, baisse tolerée "
                  f"({f1_candidat} vs {f1_actuel})")
    else:
        deployer = False
        raison = f"F1 {f1_candidat} < {f1_actuel} : modele conserve"

    print(f"Decision : {'DEPLOIEMENT' if deployer else 'CONSERVATION'} — {raison}")

    if deployer:
        os.makedirs(MODEL_DIR, exist_ok=True)
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Sauvegarde du modele sortant, pour pouvoir revenir en arriere
        for nom in ("modele_qualite.pkl", "colonnes_modele.pkl"):
            actuel = f"{MODEL_DIR}/{nom}"
            if os.path.exists(actuel):
                shutil.copy(actuel, f"{ML_DIR}/backup_{horodatage}_{nom}")

        shutil.copy(f"{ML_DIR}/modele_candidat.pkl",   f"{MODEL_DIR}/modele_qualite.pkl")
        shutil.copy(f"{ML_DIR}/colonnes_candidat.pkl", f"{MODEL_DIR}/colonnes_modele.pkl")
        print("Modele deploye. Il sera pris en compte au prochain demarrage de l'API.")

    # Tracabilite de l'entrainement
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO model_training_runs
                (trained_at, motif, n_lignes, f1, precision_score, rappel,
                 deployed, success, note)
            VALUES
                (NOW(), :motif, :lignes, :f1, :prec, :rap, :dep, TRUE, :note)
        """), {
            "motif":  motif,
            "lignes": lignes,
            "f1":     f1_candidat,
            "prec":   metriques["precision"],
            "rap":    metriques["rappel"],
            "dep":    deployer,
            "note":   raison,
        })

    return {"deploye": deployer, "raison": raison, **metriques}


# ─────────────────────────────────────────────────────────────
# DAG
# ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="reentrainement_modele",
    description="Reentraine le modele lorsque les decisions accumulees le "
                "justifient (volume ou contexte nouveau)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="0 3 * * 0",     # verification hebdomadaire, dimanche a 3h
    catchup=False,
    max_active_runs=1,
    tags=["ml", "reentrainement"],
) as dag:

    evaluer = PythonOperator(
        task_id="evaluer_declencheurs",
        python_callable=evaluer_declencheurs,
        doc_md="Verifie les deux declencheurs : volume de nouvelles decisions, "
               "ou apparition d'un contexte inconnu suffisamment documente.",
    )

    branche = BranchPythonOperator(
        task_id="brancher",
        python_callable=brancher,
    )

    construire = PythonOperator(
        task_id="construire_jeu_entrainement",
        python_callable=construire_jeu_entrainement,
        doc_md="Jeu synthetique enrichi des decisions reelles accumulees.",
    )

    entrainement = PythonOperator(
        task_id="entrainer",
        python_callable=entrainer,
        doc_md="Foret aleatoire, decoupage stratifie, ponderation des classes.",
    )

    deployer = PythonOperator(
        task_id="deployer_si_meilleur",
        python_callable=deployer_si_meilleur,
        doc_md="Le modele n'est remplace que s'il ameliore la performance, "
               "ou s'il couvre un contexte jusque-la inconnu.",
    )

    aucun = EmptyOperator(
        task_id="aucun_reentrainement",
        doc_md="Aucun declencheur atteint : le modele en service est conserve.",
    )

    evaluer >> branche >> [construire, aucun]
    construire >> entrainement >> deployer