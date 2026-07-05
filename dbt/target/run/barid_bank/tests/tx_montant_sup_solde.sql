select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      select t.transaction_id, t.compte_id, t.montant, co.solde
from "barid_bank"."public_staging"."stg_transactions" t
join "barid_bank"."public_staging"."stg_comptes" co on t.compte_id = co.compte_id
where t.montant > co.solde
      
    ) dbt_internal_test