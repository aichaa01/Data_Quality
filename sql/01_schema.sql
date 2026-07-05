-- ============================================================
-- 01_schema.sql — Creation des tables (Al Barid Bank)
-- NOTE : Pas de FK enforced pour preserver les anomalies de coherence
-- ============================================================

-- Drop dans l'ordre inverse des dependances
DROP TABLE IF EXISTS digital_usage   CASCADE;
DROP TABLE IF EXISTS transactions    CASCADE;
DROP TABLE IF EXISTS cartes          CASCADE;
DROP TABLE IF EXISTS gabs            CASCADE;
DROP TABLE IF EXISTS comptes         CASCADE;
DROP TABLE IF EXISTS clients         CASCADE;
DROP TABLE IF EXISTS agences         CASCADE;
DROP TABLE IF EXISTS admin_decisions   CASCADE;
DROP TABLE IF EXISTS rejected_records  CASCADE;
DROP TABLE IF EXISTS validated_records CASCADE;

-- ────────────────────────────────────────────
-- 1. AGENCES
-- ────────────────────────────────────────────
CREATE TABLE agences (
    agence_id       SERIAL PRIMARY KEY,
    nom_agence      VARCHAR(100) NOT NULL,
    ville           VARCHAR(100) NOT NULL,
    region          VARCHAR(100),
    date_ouverture  DATE,
    type_agence     VARCHAR(50),            -- urbaine / rurale / premium
    statut          VARCHAR(20) NOT NULL,   -- active / fermee
    date_fermeture  DATE                    -- NULL si active
);

-- ────────────────────────────────────────────
-- 2. CLIENTS
-- CIN unique et client_id PK : plus de doublons artificiels.
-- Les anomalies de contact (CONTACT_INVALIDE) restent possibles.
-- ────────────────────────────────────────────
CREATE TABLE clients (
    client_id       INTEGER NOT NULL PRIMARY KEY,
    cin             VARCHAR(20) UNIQUE NOT NULL,
    nom             VARCHAR(100),
    prenom          VARCHAR(100),
    date_naissance  DATE,
    telephone       VARCHAR(20),
    email           VARCHAR(150),
    adresse         TEXT,
    agence_id       INTEGER,               -- peut pointer vers agence fermee (anomalie)
    date_creation   DATE
);

-- ────────────────────────────────────────────
-- 3. COMPTES BANCAIRES
-- ────────────────────────────────────────────
CREATE TABLE comptes (
    compte_id       SERIAL PRIMARY KEY,
    client_id       INTEGER,               -- peut etre inexistant (anomalie)
    type_compte     VARCHAR(50),           -- courant / epargne / professionnel
    date_ouverture  DATE,
    solde           NUMERIC(15, 2),
    statut          VARCHAR(20)            -- actif / cloture / suspendu
);

-- ────────────────────────────────────────────
-- 4. CARTES BANCAIRES
-- ────────────────────────────────────────────
CREATE TABLE cartes (
    carte_id        SERIAL PRIMARY KEY,
    compte_id       INTEGER,               -- peut pointer vers compte cloture (anomalie)
    type_carte      VARCHAR(50),           -- Visa / Mastercard / CIB
    date_expiration DATE,
    statut          VARCHAR(20)            -- active / expiree / bloquee
);

-- ────────────────────────────────────────────
-- 5. GABS
-- ────────────────────────────────────────────
CREATE TABLE gabs (
    gab_id          SERIAL PRIMARY KEY,
    agence_id       INTEGER,
    type_gab        VARCHAR(50),           -- distributeur / depot / mixte
    ville           VARCHAR(100),
    statut          VARCHAR(30)            -- operationnel / en panne / hors service
);

-- ────────────────────────────────────────────
-- 6. TRANSACTIONS
-- ────────────────────────────────────────────
CREATE TABLE transactions (
    transaction_id      SERIAL PRIMARY KEY,
    compte_id           INTEGER,           -- peut etre inexistant (anomalie)
    date_transaction    TIMESTAMP,
    montant              NUMERIC(15, 2),
    type_transaction     VARCHAR(50),       -- retrait / versement / virement / paiement
    canal                VARCHAR(50),       -- agence / GAB / BBM / BaridNet
    agence_id            INTEGER,           -- NULL si canal != agence
    gab_id               INTEGER            -- NULL si canal != GAB (anomalies possibles)
);

-- ────────────────────────────────────────────
-- 7. DIGITAL USAGE
-- ────────────────────────────────────────────
CREATE TABLE digital_usage (
    usage_id        SERIAL PRIMARY KEY,
    client_id       INTEGER,               -- peut etre inexistant (anomalie)
    date_connexion  TIMESTAMP,
    canal           VARCHAR(50),           -- BBM / BaridNet
    action          VARCHAR(100)           -- consultation / virement / paiement facture / ...
);

-- ────────────────────────────────────────────
-- 8. TABLES DE GOUVERNANCE
-- cascade_from trace les decisions automatiques generees
-- par une cascade de rejet (client -> comptes -> transactions/cartes)
-- ────────────────────────────────────────────
CREATE TABLE admin_decisions (
    id            SERIAL PRIMARY KEY,
    rule_id       VARCHAR(100) NOT NULL,
    table_name    VARCHAR(100) NOT NULL,
    record_id     INTEGER      NOT NULL,
    decision      VARCHAR(10)  NOT NULL CHECK (decision IN ('accepted','rejected')),
    severity      VARCHAR(10)  NOT NULL CHECK (severity IN ('low','medium','high')),
    comment       TEXT,
    decided_at    TIMESTAMP DEFAULT NOW(),
    cascade_from  INTEGER REFERENCES admin_decisions(id)
);

CREATE TABLE rejected_records (
    id          SERIAL PRIMARY KEY,
    rule_id     VARCHAR(100) NOT NULL,
    table_name  VARCHAR(100) NOT NULL,
    record_id   INTEGER      NOT NULL,
    record_data JSONB,
    decision_id INTEGER REFERENCES admin_decisions(id),
    rejected_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE validated_records (
    id              SERIAL PRIMARY KEY,
    table_name      VARCHAR(100) NOT NULL,
    record_id       INTEGER      NOT NULL,
    decision_id     INTEGER REFERENCES admin_decisions(id),
    validated_at    TIMESTAMP DEFAULT NOW(),
    pipeline_run_id VARCHAR(100)
);

-- ────────────────────────────────────────────
-- INDEX
-- ────────────────────────────────────────────
CREATE INDEX idx_decisions_rule_id    ON admin_decisions (rule_id);
CREATE INDEX idx_decisions_decision   ON admin_decisions (decision);
CREATE INDEX idx_decisions_decided_at ON admin_decisions (decided_at);
CREATE INDEX idx_decisions_cascade    ON admin_decisions (cascade_from);
CREATE INDEX idx_rejected_rule        ON rejected_records (rule_id);
CREATE INDEX idx_rejected_table       ON rejected_records (table_name);
CREATE INDEX idx_validated_table      ON validated_records (table_name);