select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    



select usage_id
from "barid_bank"."public_staging"."stg_digital_usage"
where usage_id is null



      
    ) dbt_internal_test