select transaction_id, compte_id, date_transaction, canal, gab_id
from {{ ref('stg_transactions') }}
where canal != 'GAB' and gab_id is not null