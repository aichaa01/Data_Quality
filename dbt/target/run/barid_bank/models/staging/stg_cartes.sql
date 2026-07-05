
  create view "barid_bank"."public_staging"."stg_cartes__dbt_tmp"
    
    
  as (
    with source as (
    select * from "barid_bank"."public"."cartes"
)

select
    carte_id::integer                           as carte_id,
    compte_id::integer                          as compte_id,
    trim(type_carte)                            as type_carte,
    date_expiration::date                       as date_expiration,
    trim(statut)                                as statut,
    case when statut = 'active'
          and date_expiration < current_date
         then true else false end               as carte_expiree_mais_active
from source
  );