select client_id, nom, prenom, email, telephone
from {{ ref('stg_clients') }}
where contact_invalide = true