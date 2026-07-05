
  
    

  create  table "barid_bank"."public_dwh_metier"."fct_transaction__dbt_tmp"
  
  
    as
  
  (
    

-- Transactions valides + acceptees (on exclut les rejetes, y compris cascade)
with rejected as (
    select record_id
    from "barid_bank"."public"."admin_decisions"
    where table_name = 'transactions' and decision = 'rejected'
)

select
    t.transaction_id,
    t.compte_id,
    t.date_transaction,
    to_char(t.date_transaction, 'YYYYMMDD')::integer as date_id,
    t.montant,
    t.type_transaction,
    t.canal,
    t.agence_id,
    t.gab_id
from "barid_bank"."public_staging"."stg_transactions" t
where t.transaction_id not in (select record_id from rejected)
  );
  