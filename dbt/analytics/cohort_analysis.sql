{{ config(materialized='table') }}

with first_purchase as( 
select 
customer_unique_id,
min(full_date) as first_purchase_date
from {{ ref('fact_customer_orders') }}
group by customer_unique_id
)

,purchases_ as(    
select
fp.customer_unique_id,
fp.first_purchase_date,
f.full_date as purchases
from {{ ref('fact_customer_orders') }} f inner join first_purchase fp on f.customer_unique_id= fp.customer_unique_id
)

,month_index_ as( 
select
customer_unique_id,
first_purchase_date,
purchases,
date_diff('month',first_purchase_date,purchases) as month_index
from purchases_
)

,cohort_month as( 
select 
customer_unique_id,
strftime(first_purchase_date, '%Y-%m') AS cohort_month,
purchases,
month_index
from month_index_
)

,cohort_table as( -- creating cohort table 
select 
count(distinct customer_unique_id) as customer_count,
cohort_month,
month_index
from cohort_month
group by 
cohort_month,
month_index
)

--select * from cohort_table where cohort_month='2018-01'
--order by month_index 

,month_0 as(
select 
cohort_month,
month_index,
customer_count as customer_month0_count
from cohort_table
where month_index=0
)

,cohort_size as(
select 
c.cohort_month,
c.month_index,
c.customer_count,
m.customer_month0_count
from month_0 m join cohort_table c on c.cohort_month= m.cohort_month
order by cohort_month, month_index
)

,retention_r as(
select
cohort_month,
month_index,
customer_count,
customer_month0_count,
round(customer_count * 1.0 / customer_month0_count,4)  as retention_rate
from cohort_size
)


select * from retention_r 
order by cohort_month , month_index
