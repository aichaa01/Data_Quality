with source as (
    select * from {{ source('raw', 'gabs') }}
)

select
    gab_id::integer                             as gab_id,
    agence_id::integer                          as agence_id,
    trim(type_gab)                              as type_gab,
    trim(ville)                                 as ville,
    trim(statut)                                as statut,
    case when statut = 'operationnel' then true
         else false end                         as est_operationnel
from source