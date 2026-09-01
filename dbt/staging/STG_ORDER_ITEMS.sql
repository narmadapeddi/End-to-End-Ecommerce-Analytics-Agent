{{ config(materialized='table') }}

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value
from {{ source('raw', 'olist_order_items') }}
