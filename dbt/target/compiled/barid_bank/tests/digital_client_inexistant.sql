select du.usage_id, du.client_id, du.date_connexion, du.canal
from "barid_bank"."public_staging"."stg_digital_usage" du
where not exists (
    select 1 from "barid_bank"."public_staging"."stg_clients" cl where cl.client_id = du.client_id
)