{% snapshot clients_snapshot %}

{{
    config(
      target_schema='dwh_metier',
      unique_key='client_id',
      strategy='check',
      check_cols=['agence_id', 'telephone', 'email', 'adresse', 'cin', 'nom', 'prenom'],
      invalidate_hard_deletes=True
    )
}}

-- ============================================================
-- clients_snapshot — Historisation des clients VALIDES (SCD Type 2)
-- Al Barid Bank — Data Quality Platform
--
-- Seuls les clients valides (valides par nature ou acceptes par
-- l'administrateur) sont historises ; les rejetes sont exclus, comme dans
-- dwh_metier. dbt suit l'evolution de l'agence de rattachement et des
-- coordonnees, en versionnant chaque changement (dbt_valid_from / dbt_valid_to).
-- ============================================================

with rejected as (
    select record_id
    from {{ source('raw', 'admin_decisions') }}
    where table_name = 'clients' and decision = 'rejected'
)

select
    cl.client_id,
    cl.cin,
    cl.nom,
    cl.prenom,
    cl.date_naissance,
    cl.telephone,
    cl.email,
    cl.adresse,
    cl.agence_id,
    cl.date_creation
from {{ source('raw', 'clients') }} cl
where cl.client_id not in (select record_id from rejected)

{% endsnapshot %}