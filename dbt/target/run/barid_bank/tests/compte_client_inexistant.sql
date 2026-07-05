select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      select co.compte_id, co.client_id, co.type_compte, co.statut
from "barid_bank"."public_staging"."stg_comptes" co
where not exists (
    select 1 from "barid_bank"."public_staging"."stg_clients" cl where cl.client_id = co.client_id
)
      
    ) dbt_internal_test