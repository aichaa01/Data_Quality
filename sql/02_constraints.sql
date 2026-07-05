-- ============================================================
-- 02_constraints.sql — Index pour optimiser les requêtes
-- NOTE : Pas de FK enforced → les anomalies de cohérence
--        sont préservées pour le moteur de qualité.
-- ============================================================

-- ────────────────────────────────────────────
-- CLIENTS
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_clients_client_id   ON clients (client_id);
CREATE INDEX IF NOT EXISTS idx_clients_cin         ON clients (cin);
CREATE INDEX IF NOT EXISTS idx_clients_agence_id   ON clients (agence_id);

-- ────────────────────────────────────────────
-- COMPTES
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_comptes_client_id   ON comptes (client_id);
CREATE INDEX IF NOT EXISTS idx_comptes_statut      ON comptes (statut);

-- ────────────────────────────────────────────
-- CARTES
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_cartes_compte_id    ON cartes (compte_id);
CREATE INDEX IF NOT EXISTS idx_cartes_statut       ON cartes (statut);

-- ────────────────────────────────────────────
-- GABs
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_gabs_agence_id      ON gabs (agence_id);

-- ────────────────────────────────────────────
-- TRANSACTIONS
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_transactions_compte_id        ON transactions (compte_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date             ON transactions (date_transaction);
CREATE INDEX IF NOT EXISTS idx_transactions_canal            ON transactions (canal);
CREATE INDEX IF NOT EXISTS idx_transactions_gab_id           ON transactions (gab_id);

-- ────────────────────────────────────────────
-- DIGITAL USAGE
-- ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_digital_client_id   ON digital_usage (client_id);
CREATE INDEX IF NOT EXISTS idx_digital_date        ON digital_usage (date_connexion);
