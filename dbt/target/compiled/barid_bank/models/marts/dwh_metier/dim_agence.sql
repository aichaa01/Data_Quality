

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
from "barid_bank"."public_staging"."stg_agences"