
  create view "barid_bank"."public_staging"."stg_gabs__dbt_tmp"
    
    
  as (
    with source as (
    select * from "barid_bank"."public"."gabs"
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
  );