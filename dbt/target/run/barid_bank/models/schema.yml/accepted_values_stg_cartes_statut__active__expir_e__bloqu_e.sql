select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    

with all_values as (

    select
        statut as value_field,
        count(*) as n_records

    from "barid_bank"."public_staging"."stg_cartes"
    group by statut

)

select *
from all_values
where value_field not in (
    'active','expirée','bloquée'
)



      
    ) dbt_internal_test