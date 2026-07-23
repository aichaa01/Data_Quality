-- ============================================================
-- 04_history.sql — Historisation des entites a etat evolutif
-- Al Barid Bank — Data Quality Platform
--
-- OBJECTIF
--   Conserver l'historique complet des entites dont l'etat evolue dans le
--   temps : clients (agence, coordonnees), comptes (solde, statut), cartes
--   (statut). A chaque mise a jour d'un enregistrement, sa version precedente
--   est conservee ici avant d'etre ecrasee dans la table courante.
--
-- ARCHITECTURE A DEUX NIVEAUX
--   * Les tables METIER (clients, comptes, cartes) portent l'ETAT COURANT.
--     Elles alimentent dbt et la detection d'anomalies, qui s'appliquent
--     toujours a la derniere version connue de chaque enregistrement.
--   * Les tables d'HISTORIQUE (ci-dessous) conservent TOUTES les versions.
--     Elles alimentent l'entrepot, ou l'on peut analyser l'evolution des
--     donnees dans le temps.
--
--   transactions et digital_usage ne sont pas historisees : ce sont des
--   evenements immuables, jamais mis a jour. Elles restent en ajout simple.
--
-- CONVERSION DES CLES
--   comptes.compte_id et cartes.carte_id passent de SERIAL a INTEGER : dans un
--   pipeline d'ingestion, l'identifiant est fourni par le systeme source et
--   doit etre preserve, non regenere. clients.client_id est deja un INTEGER.
-- ============================================================

-- ────────────────────────────────────────────
-- Conversion des cles : SERIAL -> INTEGER
-- (l'identifiant provient de la source ; on cesse de l'auto-generer)
-- ────────────────────────────────────────────
ALTER TABLE comptes ALTER COLUMN compte_id DROP DEFAULT;
DROP SEQUENCE IF EXISTS comptes_compte_id_seq CASCADE;

ALTER TABLE cartes  ALTER COLUMN carte_id  DROP DEFAULT;
DROP SEQUENCE IF EXISTS cartes_carte_id_seq CASCADE;

-- ────────────────────────────────────────────
-- Cles primaires sur les entites historisees
-- (necessaires pour l'upsert « ON CONFLICT »)
-- clients possede deja sa PK ; on l'ajoute pour comptes et cartes.
-- ────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'comptes_pkey'
    ) THEN
        ALTER TABLE comptes ADD CONSTRAINT comptes_pkey PRIMARY KEY (compte_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'cartes_pkey'
    ) THEN
        ALTER TABLE cartes ADD CONSTRAINT cartes_pkey PRIMARY KEY (carte_id);
    END IF;
END $$;

-- ────────────────────────────────────────────
-- Tables d'historique
-- Memes attributs metier que la table courante, enrichis de :
--   version         numero de version de l'enregistrement (1, 2, 3, ...)
--   date_chargement horodatage de l'entree de cette version dans le systeme
--   operation       'insert' (premiere version) ou 'update' (version remplacee)
-- ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clients_history (
    version_id      SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL,
    cin             VARCHAR(20),
    nom             VARCHAR(100),
    prenom          VARCHAR(100),
    date_naissance  DATE,
    telephone       VARCHAR(20),
    email           VARCHAR(150),
    adresse         TEXT,
    agence_id       INTEGER,
    date_creation   DATE,
    version         INTEGER      NOT NULL,
    date_chargement TIMESTAMP    NOT NULL DEFAULT NOW(),
    operation       VARCHAR(10)  NOT NULL
);

CREATE TABLE IF NOT EXISTS comptes_history (
    version_id      SERIAL PRIMARY KEY,
    compte_id       INTEGER NOT NULL,
    client_id       INTEGER,
    type_compte     VARCHAR(50),
    date_ouverture  DATE,
    solde           NUMERIC(15, 2),
    statut          VARCHAR(20),
    version         INTEGER      NOT NULL,
    date_chargement TIMESTAMP    NOT NULL DEFAULT NOW(),
    operation       VARCHAR(10)  NOT NULL
);

CREATE TABLE IF NOT EXISTS cartes_history (
    version_id      SERIAL PRIMARY KEY,
    carte_id        INTEGER NOT NULL,
    compte_id       INTEGER,
    type_carte      VARCHAR(50),
    date_expiration DATE,
    statut          VARCHAR(20),
    version         INTEGER      NOT NULL,
    date_chargement TIMESTAMP    NOT NULL DEFAULT NOW(),
    operation       VARCHAR(10)  NOT NULL
);

-- ────────────────────────────────────────────
-- Index sur les cles metier et l'horodatage : les analyses temporelles
-- reconstituent la trajectoire d'un enregistrement au fil de ses versions.
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_clients_hist_id   ON clients_history (client_id, version);
CREATE INDEX IF NOT EXISTS idx_comptes_hist_id   ON comptes_history (compte_id, version);
CREATE INDEX IF NOT EXISTS idx_cartes_hist_id    ON cartes_history  (carte_id, version);
CREATE INDEX IF NOT EXISTS idx_clients_hist_date ON clients_history (date_chargement);
CREATE INDEX IF NOT EXISTS idx_comptes_hist_date ON comptes_history (date_chargement);
CREATE INDEX IF NOT EXISTS idx_cartes_hist_date  ON cartes_history  (date_chargement);