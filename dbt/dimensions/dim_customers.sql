{{ config(materialized='table') }}

select 
customer_id,
customer_unique_id,
zip_code,
city,
state
from {{ ref('STG_CUSTOMERS') }}
