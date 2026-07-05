with source as (
    select * from "barid_bank"."public"."digital_usage"
)

select
    usage_id::integer                           as usage_id,
    client_id::integer                          as client_id,
    date_connexion::timestamp                   as date_connexion,
    trim(canal)                                 as canal,
    trim(action)                                as action
from source