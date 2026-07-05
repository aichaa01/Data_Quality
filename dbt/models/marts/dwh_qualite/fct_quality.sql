{{ config(materialized='table', schema='dwh_qualite') }}

-- Une ligne par enregistrement analyse des 5 tables metier.
-- Label deduit de admin_decisions (Option B : absent = valide = accepted).
-- decision_type : 'direct' | 'cascade' | 'valide'

with all_records as (
    select 'clients'::text       as table_origine, client_id      as record_id, date_creation::timestamp   as date_ref from {{ source('raw', 'clients') }}
    union all
    select 'comptes',             compte_id,        date_ouverture::timestamp   from {{ source('raw', 'comptes') }}
    union all
    select 'cartes',              carte_id,         date_expiration::timestamp  from {{ source('raw', 'cartes') }}
    union all
    select 'transactions',        transaction_id,   date_transaction            from {{ source('raw', 'transactions') }}
    union all
    select 'digital_usage',       usage_id,         date_connexion              from {{ source('raw', 'digital_usage') }}
),

-- Derniere decision par (table, record) : on prend la decision directe en priorite,
-- sinon la cascade. distinct on garantit une seule ligne par enregistrement.
decisions as (
    select distinct on (table_name, record_id)
        table_name,
        record_id,
        rule_id,
        decision,
        severity,
        case when cascade_from is null then 'direct' else 'cascade' end as decision_type
    from {{ source('raw', 'admin_decisions') }}
    order by table_name, record_id, (cascade_from is null) desc, id asc
)

select
    r.table_origine,
    r.record_id,
    coalesce(d.rule_id, 'AUCUNE')                       as rule_id,
    coalesce(reg.dimension, 'aucune')                   as dimension,
    coalesce(d.severity, 'low')                         as severity,
    coalesce(d.decision, 'accepted')                    as label,
    coalesce(d.decision_type, 'valide')                 as decision_type,
    case when d.decision is null then true else false end as is_valide,
    to_char(r.date_ref, 'YYYYMMDD')::integer            as date_id,
    -- dq_score simplifie : 100 si valide, sinon selon severity
    case
        when d.decision is null      then 100
        when d.severity = 'low'      then 85
        when d.severity = 'medium'   then 60
        when d.severity = 'high'     then 25
        else 50
    end                                                 as dq_score
from all_records r
left join decisions d
       on r.table_origine = d.table_name and r.record_id = d.record_id
left join {{ ref('dim_regle') }} reg
       on coalesce(d.rule_id, 'AUCUNE') = reg.rule_id