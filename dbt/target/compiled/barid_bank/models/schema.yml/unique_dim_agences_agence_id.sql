
    
    

select
    agence_id as unique_field,
    count(*) as n_records

from "barid_bank"."public_marts"."dim_agences"
where agence_id is not null
group by agence_id
having count(*) > 1


