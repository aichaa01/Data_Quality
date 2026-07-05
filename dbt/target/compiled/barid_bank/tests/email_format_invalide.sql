select client_id, email
from "barid_bank"."public_staging"."stg_clients"
where email is not null
  and (email not like '%@%' or email not like '%.%')