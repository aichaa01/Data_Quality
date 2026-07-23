
      update "barid_bank"."dwh_metier"."comptes_snapshot"
    set dbt_valid_to = DBT_INTERNAL_SOURCE.dbt_valid_to
    from "comptes_snapshot__dbt_tmp100520097910" as DBT_INTERNAL_SOURCE
    where DBT_INTERNAL_SOURCE.dbt_scd_id::text = "barid_bank"."dwh_metier"."comptes_snapshot".dbt_scd_id::text
      and DBT_INTERNAL_SOURCE.dbt_change_type::text in ('update'::text, 'delete'::text)
      and "barid_bank"."dwh_metier"."comptes_snapshot".dbt_valid_to is null;

    insert into "barid_bank"."dwh_metier"."comptes_snapshot" ("compte_id", "client_id", "type_compte", "date_ouverture", "solde", "statut", "dbt_updated_at", "dbt_valid_from", "dbt_valid_to", "dbt_scd_id")
    select DBT_INTERNAL_SOURCE."compte_id",DBT_INTERNAL_SOURCE."client_id",DBT_INTERNAL_SOURCE."type_compte",DBT_INTERNAL_SOURCE."date_ouverture",DBT_INTERNAL_SOURCE."solde",DBT_INTERNAL_SOURCE."statut",DBT_INTERNAL_SOURCE."dbt_updated_at",DBT_INTERNAL_SOURCE."dbt_valid_from",DBT_INTERNAL_SOURCE."dbt_valid_to",DBT_INTERNAL_SOURCE."dbt_scd_id"
    from "comptes_snapshot__dbt_tmp100520097910" as DBT_INTERNAL_SOURCE
    where DBT_INTERNAL_SOURCE.dbt_change_type::text = 'insert'::text;

  