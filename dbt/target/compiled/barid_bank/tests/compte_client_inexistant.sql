select co.compte_id, co.client_id, co.type_compte, co.statut
from "barid_bank"."public_staging"."stg_comptes" co
where not exists (
    select 1 from "barid_bank"."public_staging"."stg_clients" cl where cl.client_id = co.client_id
)