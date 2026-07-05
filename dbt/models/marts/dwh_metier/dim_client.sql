{{ config(materialized='table', schema='dwh_metier') }}

-- Clients valides + acceptes (on exclut les rejetes)
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
    cl.date_creation,
    to_char(cl.date_creation, 'YYYYMMDD')::integer as date_creation_id
from {{ ref('stg_clients') }} cl
where cl.client_id not in (select record_id from rejected)