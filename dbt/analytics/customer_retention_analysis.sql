{{ config(materialized='table') }}

with first_and_second_purchase as(
select
customer_unique_id,
min(full_date) over(partition by customer_unique_id) as first_purchase,
lead(full_date) over(partition by customer_unique_id order by  full_date) as second_purchase,
row_number() over(partition by customer_unique_id order by full_date) as rn
from {{ ref('fact_customer_orders') }}
)

,rn_ as(
select * from first_and_second_purchase
where rn=1
)

,retention_ as(
select 
customer_unique_id,
first_purchase,
second_purchase,
date_diff('day', first_purchase,second_purchase ) as day_difference
from rn_
)

select 
customer_unique_id,
first_purchase,
second_purchase,
CASE
    WHEN second_purchase IS NULL THEN 'Not Retained'
    WHEN day_difference <= 90 THEN 'Retained'
    ELSE 'Not Retained'
END AS retained_flag
from retention_
