
    
    

select
    cin as unique_field,
    count(*) as n_records

from "barid_bank"."public_staging"."stg_clients"
where cin is not null
group by cin
having count(*) > 1


