{{ config(materialized='table', schema='dwh_metier') }}

-- Agences : on garde tout (les agences ne sont jamais rejetees)
select
    agence_id,
    nom_agence,
    ville,
    region,
    date_ouverture,
    type_agence,
    statut,
    date_fermeture
from {{ ref('stg_agences') }}