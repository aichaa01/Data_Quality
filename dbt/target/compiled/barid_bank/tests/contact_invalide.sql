select client_id, nom, prenom, email, telephone
from "barid_bank"."public_staging"."stg_clients"
where contact_invalide = true