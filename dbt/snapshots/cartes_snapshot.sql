{% snapshot cartes_snapshot %}

{{
    config(
      target_schema='dwh_metier',
      unique_key='carte_id',
      strategy='check',
      check_cols=['statut', 'type_carte', 'date_expiration', 'compte_id'],
      invalidate_hard_deletes=True
    )
}}

-- ============================================================
-- cartes_snapshot — Historisation des cartes VALIDES (SCD Type 2)
-- Al Barid Bank — Data Quality Platform
--
-- Seules les cartes validees sont historisees ; les rejetees sont exclues.
-- dbt suit l'evolution du statut de la carte (active -> expiree -> bloquee)
-- et versionne chaque changement.
-- ============================================================

with rejected as (
    select record_id
    from {{ source('raw', 'admin_decisions') }}
    where table_name = 'cartes' and decision = 'rejected'
)

select
    ca.carte_id,
    ca.compte_id,
    ca.type_carte,
    ca.date_expiration,
    ca.statut
from {{ source('raw', 'cartes') }} ca
where ca.carte_id not in (select record_id from rejected)

{% endsnapshot %}