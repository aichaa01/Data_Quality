select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    



select carte_id
from "barid_bank"."public_staging"."stg_cartes"
where carte_id is null



      
    ) dbt_internal_test