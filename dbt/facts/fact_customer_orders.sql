{{ config(materialized='table') }}

select 

o.order_id,
dc.customer_unique_id,
o.order_status,
o.order_approved_at,
o.order_delivered_carrier_date,
o.order_delivered_customer_date,
o.order_estimated_delivery_date,
dd.full_date,

sum(oi.price) as order_value,
sum(oi.freight_value) as freight_value

from {{ ref('STG_ORDERS') }} o 
join {{ ref('dim_customers') }} dc on o.customer_id=dc.customer_id
join {{ ref('STG_ORDER_ITEMS') }} oi on o.order_id=oi.order_id
join {{ ref('dim_date') }} dd on date(o.order_purchase_timestamp)=dd.full_date

group by 
o.order_id,
dc.customer_unique_id,
o.order_status,
dd.full_date,
o.order_approved_at,
o.order_delivered_carrier_date,
o.order_delivered_customer_date,
o.order_estimated_delivery_date



