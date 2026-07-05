select t.transaction_id, t.compte_id, t.date_transaction, t.montant
from "barid_bank"."public_staging"."stg_transactions" t
where not exists (
    select 1 from "barid_bank"."public_staging"."stg_comptes" c where c.compte_id = t.compte_id
)