select c.carte_id, c.compte_id, c.statut as statut_carte, co.statut as statut_compte
from "barid_bank"."public_staging"."stg_cartes" c
join "barid_bank"."public_staging"."stg_comptes" co on c.compte_id = co.compte_id
where c.statut = 'active' and co.statut = 'cloture'