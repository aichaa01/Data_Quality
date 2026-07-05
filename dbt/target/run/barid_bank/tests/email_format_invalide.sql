select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      select client_id, email
from "barid_bank"."public_staging"."stg_clients"
where email is not null
  and (email not like '%@%' or email not like '%.%')
      
    ) dbt_internal_test