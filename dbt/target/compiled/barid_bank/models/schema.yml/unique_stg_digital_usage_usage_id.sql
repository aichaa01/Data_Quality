
    
    

select
    usage_id as unique_field,
    count(*) as n_records

from "barid_bank"."public_staging"."stg_digital_usage"
where usage_id is not null
group by usage_id
having count(*) > 1


