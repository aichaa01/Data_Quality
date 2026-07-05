select du.usage_id, du.client_id, du.date_connexion, du.canal
from {{ ref('stg_digital_usage') }} du
where not exists (
    select 1 from {{ ref('stg_clients') }} cl where cl.client_id = du.client_id
)