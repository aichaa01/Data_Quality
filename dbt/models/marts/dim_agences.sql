with agences as (
    select * from {{ ref('stg_agences') }}
)

select
    agence_id, nom_agence, ville, region,
    date_ouverture, type_agence, statut,
    date_fermeture, est_fermee,
    case when est_fermee
         then date_part('year', age(date_fermeture, date_ouverture))
         else date_part('year', age(current_date, date_ouverture))
    end                                         as annees_activite
from agences