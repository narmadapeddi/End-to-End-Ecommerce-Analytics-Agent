{{ config(materialized='table') }}

with cltv as(
SELECT
    customer_unique_id,
    SUM(order_value) AS cltv
FROM {{ ref('fact_customer_orders') }}
GROUP BY customer_unique_id
)
,product_info as (
select
distinct f.customer_unique_id,
d.product_category_name_english
FROM {{ ref('fact_order_items') }} f JOIN {{ ref('dim_products') }} d on f.product_id = d.product_id
)
,product_cltv_info as(
select
c.customer_unique_id,
p.product_category_name_english,
c.cltv
from cltv c join product_info p on c.customer_unique_id = p.customer_unique_id
)

select 
product_category_name_english,
avg(cltv) as avg_cltv
from product_cltv_info
group by
product_category_name_english
order by avg_cltv desc 
