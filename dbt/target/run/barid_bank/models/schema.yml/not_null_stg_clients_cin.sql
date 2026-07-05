select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    



select cin
from "barid_bank"."public_staging"."stg_clients"
where cin is null



      
    ) dbt_internal_test