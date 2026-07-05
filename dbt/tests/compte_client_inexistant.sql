select co.compte_id, co.client_id, co.type_compte, co.statut
from {{ ref('stg_comptes') }} co
where not exists (
    select 1 from {{ ref('stg_clients') }} cl where cl.client_id = co.client_id
)