{% snapshot comptes_snapshot %}

{{
    config(
      target_schema='dwh_metier',
      unique_key='compte_id',
      strategy='check',
      check_cols=['solde', 'statut', 'type_compte', 'client_id'],
      invalidate_hard_deletes=True
    )
}}

-- ============================================================
-- comptes_snapshot — Historisation des comptes VALIDES (SCD Type 2)
-- Al Barid Bank — Data Quality Platform
--
-- L'entrepot ne conserve que les donnees validees : soit valides par nature
-- (aucune anomalie), soit acceptees par l'administrateur. Les enregistrements
-- rejetes sont exclus, exactement comme dans les dimensions de dwh_metier.
--
-- A chaque execution (declenchee par le DAG dedie, apres les decisions), dbt
-- compare l'etat courant valide avec la derniere version enregistree. Si le
-- solde, le statut, le type ou le client change, dbt clot la version
-- precedente (dbt_valid_to) et en ouvre une nouvelle. La base relationnelle,
-- elle, ne porte que l'etat courant.
-- ============================================================

with rejected as (
    select record_id
    from {{ source('raw', 'admin_decisions') }}
    where table_name = 'comptes' and decision = 'rejected'
)

select
    co.compte_id,
    co.client_id,
    co.type_compte,
    co.date_ouverture,
    co.solde,
    co.statut
from {{ source('raw', 'comptes') }} co
where co.compte_id not in (select record_id from rejected)

{% endsnapshot %}