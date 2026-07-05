select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      select client_id, nom, prenom, email, telephone
from "barid_bank"."public_staging"."stg_clients"
where contact_invalide = true
      
    ) dbt_internal_test