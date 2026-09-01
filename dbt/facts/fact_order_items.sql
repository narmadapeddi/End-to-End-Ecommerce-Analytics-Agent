{{ config(materialized='table') }}

select 

oi.order_id,
oi.order_item_id,
oi.product_id,
oi.seller_id,
o.order_status,
oi.price,
oi.freight_value,
dc.customer_unique_id,
dd.full_date


from {{ ref('STG_ORDER_ITEMS') }} oi 
join {{ ref('STG_ORDERS') }} o on o.order_id=oi.order_id
join {{ ref('dim_customers') }} dc on o.customer_id=dc.customer_id
join {{ ref('dim_date') }} dd on date(o.order_purchase_timestamp)=dd.full_date








