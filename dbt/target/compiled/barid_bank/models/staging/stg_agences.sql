with source as (
    select * from "barid_bank"."public"."agences"
)

select
    agence_id::integer                          as agence_id,
    trim(nom_agence)                            as nom_agence,
    trim(ville)                                 as ville,
    trim(region)                                as region,
    date_ouverture::date                        as date_ouverture,
    trim(type_agence)                           as type_agence,
    trim(statut)                                as statut,
    date_fermeture::date                        as date_fermeture,
    case when statut = 'fermee' then true
         else false end                         as est_fermee
from source