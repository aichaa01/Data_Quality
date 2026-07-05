select t.transaction_id, t.compte_id, t.date_transaction, t.montant
from {{ ref('stg_transactions') }} t
where not exists (
    select 1 from {{ ref('stg_comptes') }} c where c.compte_id = t.compte_id
)