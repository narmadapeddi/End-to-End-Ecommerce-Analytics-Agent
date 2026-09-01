{{ config(materialized='table') }}

select
    customer_id,
    customer_unique_id,
    cast(customer_zip_code_prefix as varchar) as zip_code,
    customer_city as city,
    customer_state as state
from {{ source('raw', 'olist_customers') }}
