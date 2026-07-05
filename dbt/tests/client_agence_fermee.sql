select cl.client_id, cl.nom, cl.prenom, cl.agence_id,
       a.nom_agence, a.statut, a.date_fermeture
from {{ ref('stg_clients') }} cl
join {{ ref('stg_agences') }} a on cl.agence_id = a.agence_id
where a.statut = 'fermee'