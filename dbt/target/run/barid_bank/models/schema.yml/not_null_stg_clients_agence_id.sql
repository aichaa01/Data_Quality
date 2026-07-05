select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    



select agence_id
from "barid_bank"."public_staging"."stg_clients"
where agence_id is null



      
    ) dbt_internal_test