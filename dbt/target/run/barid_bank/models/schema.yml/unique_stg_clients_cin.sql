select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
    

select
    cin as unique_field,
    count(*) as n_records

from "barid_bank"."public_staging"."stg_clients"
where cin is not null
group by cin
having count(*) > 1



      
    ) dbt_internal_test