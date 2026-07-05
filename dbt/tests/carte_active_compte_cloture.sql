select c.carte_id, c.compte_id, c.statut as statut_carte, co.statut as statut_compte
from {{ ref('stg_cartes') }} c
join {{ ref('stg_comptes') }} co on c.compte_id = co.compte_id
where c.statut = 'active' and co.statut = 'cloture'