

-- Dimension temps : couvre 2015-2026 (donnees generees + marge)
with dates as (
    select generate_series(
        '2015-01-01'::date,
        '2026-12-31'::date,
        '1 day'::interval
    )::date as date_jour
)

select
    to_char(date_jour, 'YYYYMMDD')::integer as date_id,
    date_jour,
    extract(year    from date_jour)::integer as annee,
    extract(month   from date_jour)::integer as mois,
    extract(day     from date_jour)::integer as jour,
    extract(quarter from date_jour)::integer as trimestre,
    extract(dow     from date_jour)::integer as jour_semaine,
    to_char(date_jour, 'TMMonth')            as nom_mois,
    to_char(date_jour, 'TMDay')              as nom_jour
from dates