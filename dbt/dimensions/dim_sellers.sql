{{ config(materialized='table') }}

select 
seller_id,
seller_city,
seller_state,
seller_zip_code_prefix
from {{ ref('STG_SELLERS') }}
