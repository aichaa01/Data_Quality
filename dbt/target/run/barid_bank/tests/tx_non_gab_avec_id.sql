select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      select transaction_id, compte_id, date_transaction, canal, gab_id
from "barid_bank"."public_staging"."stg_transactions"
where canal != 'GAB' and gab_id is not null
      
    ) dbt_internal_test