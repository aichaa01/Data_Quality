-- ============================================================
-- 04_keys.sql — Conversion des cles pour l'ingestion
-- Al Barid Bank — Data Quality Platform
--
-- Dans un pipeline d'ingestion, l'identifiant d'un enregistrement est fourni
-- par le systeme source et doit etre preserve, non regenere. Les cles des
-- entites a etat evolutif passent donc de SERIAL a INTEGER, et recoivent une
-- cle primaire, necessaire a l'upsert (« ON CONFLICT ») lors du chargement.
--
-- La base relationnelle ne porte que l'ETAT COURANT : une mise a jour ecrase
-- la version precedente. L'historique n'est pas conserve ici, mais dans
-- l'entrepot, au moyen d'un snapshot dbt.
-- ============================================================

-- ────────────────────────────────────────────
-- Conversion SERIAL -> INTEGER
-- (on cesse d'auto-generer l'identifiant : il vient de la source)
-- ────────────────────────────────────────────
ALTER TABLE comptes ALTER COLUMN compte_id DROP DEFAULT;
DROP SEQUENCE IF EXISTS comptes_compte_id_seq CASCADE;

ALTER TABLE cartes  ALTER COLUMN carte_id  DROP DEFAULT;
DROP SEQUENCE IF EXISTS cartes_carte_id_seq CASCADE;

-- ────────────────────────────────────────────
-- Cles primaires (necessaires a l'upsert)
-- clients possede deja sa cle primaire.
-- ────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'comptes_pkey') THEN
        ALTER TABLE comptes ADD CONSTRAINT comptes_pkey PRIMARY KEY (compte_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cartes_pkey') THEN
        ALTER TABLE cartes ADD CONSTRAINT cartes_pkey PRIMARY KEY (carte_id);
    END IF;
END $$;
