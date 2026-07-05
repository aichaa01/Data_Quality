
    
    

select
    gab_id as unique_field,
    count(*) as n_records

from "barid_bank"."public_staging"."stg_gabs"
where gab_id is not null
group by gab_id
having count(*) > 1


