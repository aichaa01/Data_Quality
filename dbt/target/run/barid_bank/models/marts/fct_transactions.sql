
  
    

  create  table "barid_bank"."public_marts"."fct_transactions__dbt_tmp"
  
  
    as
  
  (
    with transactions as (
    select * from "barid_bank"."public_staging"."stg_transactions"
),
comptes as (
    select compte_id, client_id, solde, statut from "barid_bank"."public_staging"."stg_comptes"
),
gabs as (
    select gab_id, ville as ville_gab, statut as statut_gab from "barid_bank"."public_staging"."stg_gabs"
)

select
    t.transaction_id, t.compte_id, t.date_transaction,
    date_part('year',  t.date_transaction)      as annee,
    date_part('month', t.date_transaction)      as mois,
    date_part('day',   t.date_transaction)      as jour,
    t.montant, t.type_transaction, t.canal,
    t.agence_id, t.gab_id, g.ville_gab, g.statut_gab,
    co.client_id, co.solde as solde_compte, co.statut as statut_compte,
    t.gab_sans_id, t.non_gab_avec_id,
    case when co.compte_id is null then true else false end  as compte_inexistant,
    100
    - case when t.gab_sans_id        then 10 else 0 end
    - case when t.non_gab_avec_id    then 15 else 0 end
    - case when co.compte_id is null then 50 else 0 end
                                                as dq_score
from transactions t
left join comptes co on t.compte_id = co.compte_id
left join gabs    g  on t.gab_id    = g.gab_id
  );
  