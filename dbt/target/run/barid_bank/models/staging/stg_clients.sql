
  create view "barid_bank"."public_staging"."stg_clients__dbt_tmp"
    
    
  as (
    with source as (
    select * from "barid_bank"."public"."clients"
)

select
    client_id::integer                          as client_id,
    trim(cin)                                   as cin,
    trim(nom)                                   as nom,
    trim(prenom)                                as prenom,
    date_naissance::date                        as date_naissance,
    trim(telephone)                             as telephone,
    lower(trim(email))                          as email,
    trim(adresse)                               as adresse,
    agence_id::integer                          as agence_id,
    date_creation::date                         as date_creation,

    case when email is null or email = ''
         then true else false end               as email_manquant,
    case when telephone is null or telephone = ''
         then true else false end               as telephone_manquant,
    case when adresse is null or adresse = ''
         then true else false end               as adresse_manquante,
    case when email is not null
          and (email not like '%@%' or email not like '%.%')
         then true else false end               as email_invalide,

    -- CONTACT_INVALIDE : aucun moyen de contact valide
    -- (telephone NULL ET email invalide ou absent)
    case when telephone is null
          and (email is null or email not like '%@%' or email not like '%.%')
         then true else false end               as contact_invalide
from source
  );