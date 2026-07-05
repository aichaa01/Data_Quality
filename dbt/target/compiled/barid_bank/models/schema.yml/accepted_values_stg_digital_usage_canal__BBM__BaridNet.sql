
    
    

with all_values as (

    select
        canal as value_field,
        count(*) as n_records

    from "barid_bank"."public_staging"."stg_digital_usage"
    group by canal

)

select *
from all_values
where value_field not in (
    'BBM','BaridNet'
)


