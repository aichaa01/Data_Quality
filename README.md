# Plateforme de Gestion de la Qualité des Données — Al Barid Bank

Plateforme de contrôle et de suivi de la qualité des données bancaires, développée
dans le cadre d'un Projet de Fin d'Année (PFA). Elle simule l'environnement de données
d'Al Barid Bank et met en place un pipeline complet allant de la génération de données
synthétiques jusqu'à la constitution d'un entrepôt de données décisionnel, en passant
par la détection d'anomalies et la décision humaine assistée.

---

## Contexte

Dans un environnement bancaire, les données constituent un actif stratégique pour le
reporting, le pilotage et la conformité réglementaire. Cependant, les données issues de
différents systèmes sources présentent souvent des anomalies (valeurs manquantes,
incohérences métier, références orphelines) qui compromettent la fiabilité des analyses.

La particularité de ce projet réside dans son approche : **les données de reporting ne
peuvent être ni rejetées silencieusement (comme le ferait une contrainte d'intégrité),
ni corrigées automatiquement (comme le ferait un ETL classique)**. Modifier le contenu
d'une donnée financière serait inadmissible dans un contexte bancaire réglementé. La
plateforme adopte donc une logique de **décision humaine assistée** : elle détecte,
qualifie et documente les anomalies, puis laisse au responsable métier le soin de
décider, selon l'objectif de son analyse, si une anomalie doit être acceptée ou rejetée.

---

## Fonctionnalités

- **Génération de données synthétiques** réalistes avec anomalies contrôlées injectées volontairement
- **Profilage des données** selon des métriques génériques (complétude, unicité, fraîcheur) et des contrôles métier cross-tables
- **Détection d'anomalies** via des règles de qualité métier appliquées par dbt
- **Décision humaine** via une interface web : acceptation ou rejet de chaque anomalie
- **Rejet en cascade** : le rejet d'un enregistrement parent propage automatiquement le rejet à ses descendants (client → comptes → transactions, cartes, usages digitaux)
- **Labélisation automatique** pour constituer un jeu de données étiqueté
- **Entrepôt de données décisionnel** structuré en deux data marts : un dédié aux données métier certifiées, un dédié au pilotage de la qualité

---

## Architecture

Le pipeline suit la logique suivante :

```
   Génération de données synthétiques (avec anomalies)
                    |
                    v
   Base de données relationnelle (BDR, sans contraintes d'intégrité référentielle)
                    |
                    v
   Profilage (métriques génériques + contrôles métier)
                    |
                    v
   STAGING (vues de nettoyage + calcul de flags d'anomalie par ligne)
                    |
                    v
   DÉTECTION (tables enrichies avec score de qualité + tests de règles métier)
                    |
                    v
   DÉCISION (interface web : acceptation / rejet, avec propagation en cascade)
                    |
                    v
   LABÉLISATION (journal des décisions : accepted / rejected)
                    |
        +-----------+-----------+
        v                       v
   DATA MART MÉTIER        DATA MART QUALITÉ
   (valides + acceptés)    (tout : valides + acceptés + rejetés,
                            avec labels et métadonnées qualité)
```

La base de données relationnelle est **volontairement construite sans contraintes de
clés étrangères**. L'objectif n'est pas d'empêcher les anomalies d'entrer, mais de les
détecter, les qualifier et les soumettre à une décision. Une contrainte d'intégrité
rejetterait silencieusement les enregistrements incohérents sans jamais les analyser.

---

## Stack technique

| Composant | Technologie |
|---|---|
| Base de données | PostgreSQL 16 |
| Génération de données | Python, Faker, NumPy, Pandas |
| Transformation & tests qualité | dbt (data build tool) 1.8 |
| API & interface web | FastAPI, HTML/CSS/JavaScript |
| Conteneurisation | Docker, Docker Compose |

---

## Prérequis

- **Docker** et **Docker Compose** installés
- Aucune autre dépendance : tout s'exécute dans des conteneurs

Vérifier l'installation :

```bash
docker --version
docker-compose --version
```

---

## Installation

Cloner le dépôt et se placer dans le dossier :

```bash
git clone <url-du-depot>
cd data-quality-bank
```

Le premier lancement construit automatiquement les images Docker nécessaires.

---

## Utilisation pas à pas

Les étapes doivent être exécutées dans l'ordre. Chaque commande correspond à une phase
du pipeline.

> **Note Windows / PowerShell** : les commandes ci-dessous sont compatibles PowerShell.
> Pour les redirections de fichiers SQL, utiliser `Get-Content fichier.sql | docker exec -i ...`
> plutôt que l'opérateur `<`.

### 1. Démarrer la base de données

```bash
docker-compose up -d postgres
```

La base est initialisée automatiquement avec le schéma (`sql/01_schema.sql`) au premier
démarrage.

### 2. Générer les données synthétiques

```bash
docker-compose run --rm app python scripts/generate_data.py
```

Génère les fichiers CSV dans `data/raw/` : 20 agences, 5 000 clients, 7 000 comptes,
6 500 cartes, 100 GAB, 100 000 transactions, 50 000 usages digitaux, avec des anomalies
contrôlées injectées.

### 3. Charger les données dans PostgreSQL

```bash
docker-compose --profile load up
```

Charge les CSV dans la base relationnelle (168 620 lignes au total).

### 4. Profilage des données

```bash
docker-compose run --rm app python scripts/profiling.py
```

Produit un rapport de profilage dans `data/processed/` (métriques génériques et
comptage des anomalies métier).

### 5. Transformation et tests qualité (dbt)

```bash
docker-compose --profile dbt up dbt
```

Construit les vues de staging, les tables de détection enrichies (avec score de qualité),
et exécute les tests de règles métier. Les tests de règles métier « échouent »
volontairement : chaque échec correspond à des anomalies correctement détectées.

### 6. Labélisation automatique

```bash
docker-compose run --rm app python scripts/label_decisions.py
```

Applique les décisions (acceptation/rejet) sur les anomalies détectées, selon les règles
définies, avec propagation en cascade. Alimente le journal des décisions
(`admin_decisions`).

> Pour repartir d'un journal vierge avant relance :
> ```bash
> docker exec -i barid_bank_db psql -U admin -d barid_bank -c "TRUNCATE admin_decisions RESTART IDENTITY CASCADE; TRUNCATE rejected_records RESTART IDENTITY CASCADE;"
> ```

### 7. Construire les deux data marts

```bash
docker-compose --profile dbt up dbt
```

La même commande dbt construit également les deux data marts (`dwh_qualite` et
`dwh_metier`) à partir du journal de décisions.

### 8. Lancer l'interface web

```bash
docker-compose --profile api up -d
```

L'interface est accessible sur **http://localhost:8000**. Elle permet de consulter le
tableau de bord, d'inspecter les anomalies et de prendre des décisions.

---

## Structure du projet

```
data-quality-bank/
├── docker-compose.yml          # Orchestration des services
├── Dockerfile                  # Image Python commune
├── requirements.txt            # Dépendances Python
│
├── sql/
│   └── 01_schema.sql           # Schéma de la base relationnelle (BDR)
│
├── scripts/
│   ├── generate_data.py        # Génération des données synthétiques
│   ├── load_to_postgres.py     # Chargement des CSV dans PostgreSQL
│   ├── profiling.py            # Profilage des données
│   └── label_decisions.py      # Labélisation automatique + cascade
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── schema.yml          # Sources + tests génériques
│       ├── staging/            # 7 vues de nettoyage (stg_*)
│       ├── marts/              # 4 tables de détection (dim_*, fct_*)
│       │   ├── dwh_qualite/    # Data mart qualité (fct_quality, dim_regle, dim_temps)
│       │   └── dwh_metier/     # Data mart métier (dim_client, dim_compte, ...)
│       └── ../tests/           # 8 tests de règles métier
│
├── app/
│   ├── main.py                 # Point d'entrée FastAPI
│   ├── services/
│   │   └── db.py               # Connexion PostgreSQL
│   ├── routers/
│   │   ├── anomalies.py        # Endpoints anomalies en attente
│   │   ├── dashboard.py        # Endpoints KPIs
│   │   └── decisions.py        # Endpoints décisions + cascade
│   └── frontend/               # Interface web (HTML/CSS/JS)
│
└── data/
    ├── raw/                    # CSV générés
    └── processed/              # Rapports de profilage
```

---

## Règles métier

Huit règles de qualité sont appliquées, réparties sur deux dimensions :

| Règle | Dimension | Description | Décision par défaut |
|---|---|---|---|
| `TX_GAB_SANS_ID` | Cohérence | Transaction GAB sans identifiant de guichet | Acceptée |
| `TX_NON_GAB_AVEC_ID` | Cohérence | Transaction non-GAB avec identifiant de guichet | Acceptée |
| `CARTE_ACTIVE_COMPTE_CLOTURE` | Cohérence | Carte active sur un compte clôturé | Rejetée |
| `TX_COMPTE_INEXISTANT` | Cohérence | Transaction référençant un compte absent | Rejetée |
| `CLIENT_AGENCE_FERMEE` | Cohérence | Client rattaché à une agence fermée | Acceptée |
| `COMPTE_CLIENT_INEXISTANT` | Cohérence | Compte référençant un client absent | Rejetée |
| `DIGITAL_CLIENT_INEXISTANT` | Cohérence | Usage digital référençant un client absent | Rejetée |
| `CONTACT_INVALIDE` | Exactitude | Client sans moyen de contact valide (email invalide ET téléphone absent) | Rejetée |

**Rejet en cascade** : le rejet d'un client entraîne le rejet de ses comptes,
transactions, cartes et usages digitaux. Le rejet d'un compte entraîne le rejet de ses
transactions et cartes.

---

## Schémas de la base de données

La base `barid_bank` est organisée en cinq schémas :

| Schéma | Contenu |
|---|---|
| `public` | Base relationnelle (BDR) : 7 tables métier + journal des décisions |
| `public_staging` | 7 vues de nettoyage (staging dbt) |
| `public_marts` | 4 tables de détection enrichies avec score de qualité |
| `public_dwh_qualite` | Data mart qualité : `fct_quality`, `dim_regle`, `dim_temps` |
| `public_dwh_metier` | Data mart métier : `dim_client`, `dim_compte`, `dim_agence`, `fct_transaction` |

> Le préfixe `public_` provient du comportement par défaut de dbt qui concatène le schéma
> cible au schéma de base.

---

## Accès à la base de données

Ouvrir une session interactive :

```bash
docker exec -it barid_bank_db psql -U admin -d barid_bank
```

Commandes psql utiles :

```sql
\dn                          -- Lister les schémas
\dt public.*                 -- Tables de la BDR
\dv public_staging.*         -- Vues de staging
\dt public_dwh_qualite.*     -- Tables du data mart qualité
\d public_dwh_qualite.fct_quality   -- Structure d'une table
\q                           -- Quitter
```

Exemple : répartition des labels dans le data mart qualité :

```sql
SELECT label, decision_type, COUNT(*)
FROM public_dwh_qualite.fct_quality
GROUP BY label, decision_type
ORDER BY label, decision_type;
```

**Paramètres de connexion** (pour un client externe comme DBeaver ou pgAdmin) :

| Paramètre | Valeur |
|---|---|
| Hôte | `localhost` |
| Port | `5432` |
| Base | `barid_bank` |
| Utilisateur | `admin` |
| Mot de passe | `admin123` |

---

## Roadmap

Les composants suivants sont prévus dans les prochaines phases du projet :

- [ ] **Modèle de classification (Machine Learning)** : prédiction de la décision
  (acceptation/rejet) sur les nouveaux enregistrements, à partir du data mart qualité
- [ ] **Reporting Power BI** : tableaux de bord de pilotage de la qualité connectés au
  data mart qualité
- [ ] **Orchestration (Airflow)** : automatisation de l'ensemble du pipeline

---

## NB

Les données manipulées sont **entièrement synthétiques** et ne correspondent à aucune
donnée réelle d'Al Barid Bank.
