with clients as (
    select * from {{ ref('stg_clients') }}
),
agences as (
    select * from {{ ref('stg_agences') }}
)

select
    cl.client_id, cl.cin, cl.nom, cl.prenom, cl.date_naissance,
    cl.telephone, cl.email, cl.adresse, cl.date_creation,
    cl.agence_id, a.nom_agence, a.ville, a.region,
    a.statut                                    as statut_agence,
    cl.email_manquant, cl.telephone_manquant, cl.adresse_manquante,
    cl.email_invalide, cl.contact_invalide,
    case when a.statut = 'fermee' then true
         else false end                         as agence_fermee,
    100
    - case when cl.email_manquant     then 10 else 0 end
    - case when cl.telephone_manquant then 10 else 0 end
    - case when cl.adresse_manquante  then 10 else 0 end
    - case when cl.contact_invalide   then 40 else 0 end
    - case when a.statut = 'fermee'   then 20 else 0 end
                                                as dq_score
from clients cl
left join agences a on cl.agence_id = a.agence_id