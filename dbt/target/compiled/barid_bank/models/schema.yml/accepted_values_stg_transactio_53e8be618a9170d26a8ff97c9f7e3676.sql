
    
    

with all_values as (

    select
        canal as value_field,
        count(*) as n_records

    from "barid_bank"."public_staging"."stg_transactions"
    group by canal

)

select *
from all_values
where value_field not in (
    'agence','GAB','BBM','BaridNet'
)


