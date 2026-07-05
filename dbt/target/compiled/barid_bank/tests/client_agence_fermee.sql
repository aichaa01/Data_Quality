select cl.client_id, cl.nom, cl.prenom, cl.agence_id,
       a.nom_agence, a.statut, a.date_fermeture
from "barid_bank"."public_staging"."stg_clients" cl
join "barid_bank"."public_staging"."stg_agences" a on cl.agence_id = a.agence_id
where a.statut = 'fermee'