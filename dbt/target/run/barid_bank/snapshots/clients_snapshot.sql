
      update "barid_bank"."dwh_metier"."clients_snapshot"
    set dbt_valid_to = DBT_INTERNAL_SOURCE.dbt_valid_to
    from "clients_snapshot__dbt_tmp100520101158" as DBT_INTERNAL_SOURCE
    where DBT_INTERNAL_SOURCE.dbt_scd_id::text = "barid_bank"."dwh_metier"."clients_snapshot".dbt_scd_id::text
      and DBT_INTERNAL_SOURCE.dbt_change_type::text in ('update'::text, 'delete'::text)
      and "barid_bank"."dwh_metier"."clients_snapshot".dbt_valid_to is null;

    insert into "barid_bank"."dwh_metier"."clients_snapshot" ("client_id", "cin", "nom", "prenom", "date_naissance", "telephone", "email", "adresse", "agence_id", "date_creation", "dbt_updated_at", "dbt_valid_from", "dbt_valid_to", "dbt_scd_id")
    select DBT_INTERNAL_SOURCE."client_id",DBT_INTERNAL_SOURCE."cin",DBT_INTERNAL_SOURCE."nom",DBT_INTERNAL_SOURCE."prenom",DBT_INTERNAL_SOURCE."date_naissance",DBT_INTERNAL_SOURCE."telephone",DBT_INTERNAL_SOURCE."email",DBT_INTERNAL_SOURCE."adresse",DBT_INTERNAL_SOURCE."agence_id",DBT_INTERNAL_SOURCE."date_creation",DBT_INTERNAL_SOURCE."dbt_updated_at",DBT_INTERNAL_SOURCE."dbt_valid_from",DBT_INTERNAL_SOURCE."dbt_valid_to",DBT_INTERNAL_SOURCE."dbt_scd_id"
    from "clients_snapshot__dbt_tmp100520101158" as DBT_INTERNAL_SOURCE
    where DBT_INTERNAL_SOURCE.dbt_change_type::text = 'insert'::text;

  