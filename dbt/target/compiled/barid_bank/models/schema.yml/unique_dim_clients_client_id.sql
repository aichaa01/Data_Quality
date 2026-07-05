
    
    

select
    client_id as unique_field,
    count(*) as n_records

from "barid_bank"."public_marts"."dim_clients"
where client_id is not null
group by client_id
having count(*) > 1


