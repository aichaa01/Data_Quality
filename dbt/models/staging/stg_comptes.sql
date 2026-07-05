with source as (
    select * from {{ source('raw', 'comptes') }}
)

select
    compte_id::integer                          as compte_id,
    client_id::integer                          as client_id,
    trim(type_compte)                           as type_compte,
    date_ouverture::date                        as date_ouverture,
    solde::numeric(15,2)                        as solde,
    trim(statut)                                as statut,
    case when statut = 'cloture' then true
         else false end                         as est_cloture
from source