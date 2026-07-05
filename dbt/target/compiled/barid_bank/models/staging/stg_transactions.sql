with source as (
    select * from "barid_bank"."public"."transactions"
)

select
    transaction_id::integer                     as transaction_id,
    compte_id::integer                          as compte_id,
    date_transaction::timestamp                 as date_transaction,
    montant::numeric(15,2)                      as montant,
    trim(type_transaction)                      as type_transaction,
    trim(canal)                                 as canal,
    agence_id::integer                          as agence_id,
    gab_id::integer                             as gab_id,

    case when canal = 'GAB' and gab_id is null
         then true else false end               as gab_sans_id,
    case when canal != 'GAB' and gab_id is not null
         then true else false end               as non_gab_avec_id
from source