select transaction_id, compte_id, date_transaction, canal, gab_id
from "barid_bank"."public_staging"."stg_transactions"
where canal = 'GAB' and gab_id is null