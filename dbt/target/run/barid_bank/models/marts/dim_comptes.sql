
  
    

  create  table "barid_bank"."public_marts"."dim_comptes__dbt_tmp"
  
  
    as
  
  (
    with comptes as (
    select * from "barid_bank"."public_staging"."stg_comptes"
),
clients as (
    select client_id from "barid_bank"."public_staging"."stg_clients"
)

select
    co.compte_id, co.client_id, co.type_compte,
    co.date_ouverture, co.solde, co.statut, co.est_cloture,
    case when cl.client_id is null then true
         else false end                         as client_inexistant,
    100
    - case when cl.client_id is null then 50 else 0 end
                                                as dq_score
from comptes co
left join clients cl on co.client_id = cl.client_id
  );
  