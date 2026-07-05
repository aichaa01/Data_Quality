

-- Comptes valides + acceptes (on exclut les rejetes, y compris cascade)
with rejected as (
    select record_id
    from "barid_bank"."public"."admin_decisions"
    where table_name = 'comptes' and decision = 'rejected'
)

select
    co.compte_id,
    co.client_id,
    co.type_compte,
    co.date_ouverture,
    co.solde,
    co.statut,
    to_char(co.date_ouverture, 'YYYYMMDD')::integer as date_ouverture_id
from "barid_bank"."public_staging"."stg_comptes" co
where co.compte_id not in (select record_id from rejected)