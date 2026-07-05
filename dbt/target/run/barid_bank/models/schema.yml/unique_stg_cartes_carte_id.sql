select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    

select
    carte_id as unique_field,
    count(*) as n_records

from "barid_bank"."public_staging"."stg_cartes"
where carte_id is not null
group by carte_id
having count(*) > 1



      
    ) dbt_internal_test