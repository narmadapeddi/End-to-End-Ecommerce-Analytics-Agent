# Governed Business Metrics and Analytical Definitions

> **Business-definition authority:** This file is the authoritative source for governed business metrics, formulas, status scope, and analytical assumptions. The AI analytics agent must not silently redefine these metrics.

Use [`data_catalog.md`](data_catalog.md) as the authority for table grain, keys,
relationships, and safe joins. Business definitions in this file take precedence
over inferences from database contents or existing SQL. Technical implementation
notes explain how the current DuckDB/dbt project supports a definition; they do
not redefine it.

## Shared governed assumptions

- A customer is identified by `customer_unique_id`, not `customer_id`.
- Repeat customers have more than one order; customers with exactly one order
  are one-time customers.
- Retention uses the first and second purchases and a 90-day window.
- CLTV is historical value from recorded transactions, not a prediction of
  future spending.
- Revenue is based on item `price` aggregated to the required analytical grain.
- Freight is separate from product revenue.
- Product and seller analysis operates at order-item grain.
- Customer, order, and fulfillment analysis operates at order grain.
- Valid business nulls must not be removed automatically.
- Status scope must follow the governed definition for the metric. The agent must
  not infer a status filter merely from the values available in a table.

Technical caveats shared by multiple metrics:

- `fact_customer_orders` contains item-bearing orders only. It excludes 775
  source orders that have no item records.
- `fact_customer_orders.order_value` excludes freight.
- Monetary values are `DOUBLE`; tiny floating-point differences can occur.
- `fact_order_items` is item grain. Counting its rows does not count orders.
- A fact-to-`dim_customers` join on `customer_unique_id` is unsafe because that
  field is not unique in `dim_customers`.

## Customer identity and customer count

**Business definition**

A customer is one distinct `customer_unique_id`. The dataset can assign different
`customer_id` values to different orders placed by the same individual, so
`customer_id` must not be used for customer-centric counts.

**Formula**

```sql
count(distinct customer_unique_id)
```

**Preferred source and grain**

- Source: `fact_customer_orders`
- Required grain: order grain before distinct customer aggregation

**Status scope**

No universal customer-count status scope is governed here. It must follow the
question or the governed metric that consumes the customer count.

**Caveats**

The current fact-based population contains only customers with item-bearing
orders. Do not join the fact to `dim_customers` on `customer_unique_id` to obtain
this count.

**Validated reference value**

- Total item-bearing customers in the current fact scope: **95,420**

## Repeat Purchase Rate

**Business definition**

A repeat customer is a `customer_unique_id` with more than one order. A one-time
customer has exactly one order.

**Formula**

```text
Repeat Purchase Rate = Repeat Customers / Total Customers
```

Technical pattern:

```sql
with customer_orders as (
    select customer_unique_id, count(*) as order_count
    from fact_customer_orders
    group by customer_unique_id
)
select
    count(*) filter (where order_count > 1) * 1.0 / count(*)
from customer_orders
```

**Preferred source and grain**

- Source: `fact_customer_orders`
- Required grain: count orders per `customer_unique_id`, then customer grain

**Status scope**

The business definition does not explicitly specify an order-status filter. The
current validated implementation counts all item-bearing orders regardless of
status. This is an implementation assumption, not a newly governed status rule.

**Validated reference values under the current implementation scope**

- Total customers: **95,420**
- One-time customers: **92,507**
- Repeat customers: **2,913**
- Repeat Purchase Rate: **3.0528%**

## Customer Retention

**Business definition**

A customer is retained when their second purchase occurs within 90 days of their
first purchase. Only the first and second purchases are considered. Day 90 is
inside the governed window.

**Formula**

```text
Retained = second_purchase is not null
           and days_between(first_purchase, second_purchase) <= 90

Overall 90-Day Retention = Retained Customers / Total Customers
```

**Preferred source and grain**

- Preferred governed output: `customer_retention_analysis`
- Underlying source: `fact_customer_orders`
- Required output grain: one row per `customer_unique_id`

**Status scope**

The business definition does not explicitly name an order-status filter. The
current dbt model uses all item-bearing orders regardless of status. This remains
an implementation ambiguity requiring business confirmation.

**Assumptions and caveats**

- The model uses purchase dates, not timestamps. Same-day first and second
  purchases have a zero-day difference.
- Repeat customers whose second purchase occurs after 90 days are not retained
  under this definition.
- Customers represented only by an order without item rows cannot enter the
  current fact-based calculation.

**Validated reference values under the current implementation scope**

- Total customers: **95,420**
- Retained within 90 days: **1,992**
- Not retained: **93,428**
- Customers with no second purchase: **92,507**
- Overall 90-day retention: **2.0876%**

## Customer Lifetime Value (CLTV)

**Business definition**

Customer Lifetime Value is the total revenue generated by a customer across all
recorded purchases within the dataset. It measures historical customer value
only and does not predict future spending.

**Formula**

```sql
CLTV = sum(order_value)
```

grouped by `customer_unique_id`.

**Preferred source and grain**

- Source: `fact_customer_orders`
- Calculation grain: order grain
- Output grain: one row per `customer_unique_id`

**Status scope**

The phrase "all recorded purchases" does not explicitly enumerate statuses. The
current implementation includes all item-bearing order statuses. Confirmation is
needed before treating that implementation detail as a governed status rule.

**Assumptions and caveats**

- `order_value` is item-price revenue and excludes freight.
- The calculation excludes orders without item rows because they do not appear
  in `fact_customer_orders`.
- Values are historical within the dataset observation window.
- `DOUBLE` aggregation may create tiny floating-point differences.

**Validated reference values under the current implementation scope**

- One-time average historical CLTV: **138.67**
- Repeat average historical CLTV: **262.03**

### Category-associated average CLTV

`product_cltv_analysis` is an existing technical output, not a redefinition of
customer CLTV. It reports the average total customer CLTV among customers who
purchased from each English product category. It does **not** report revenue
generated within that category. A customer's full CLTV is associated with each
distinct category they purchased, and the model retains a null-category group.

## Average Order Value (AOV)

**Business definition**

Average revenue generated per delivered order. Governed AOV must not use all
order statuses.

**Formula**

```text
AOV = Delivered Revenue / Delivered Orders
```

Equivalent fact calculation:

```sql
select sum(order_value) / count(distinct order_id)
from fact_customer_orders
where order_status = 'delivered'
```

**Preferred source and grain**

- Source: `fact_customer_orders`
- Required grain: delivered order grain

**Required filter/status scope**

```sql
order_status = 'delivered'
```

The numerator and denominator must use this same filter.

**Assumptions and caveats**

- Delivered revenue is `order_value`, excluding freight.
- The fact contains item-bearing orders. All currently validated delivered
  source orders are represented in the fact.
- Do not use the all-status order-value total as delivered revenue.

**Read-only validated reference values**

- Delivered item-bearing orders: **96,478**
- Delivered revenue: **13,221,498.11**
- Governed delivered AOV: **137.04**

## Customer Segmentation

**Business definition**

Customers are segmented using purchase frequency and historical CLTV.

Governed segment names:

- High-Value Loyal Customers
- Potential Loyal Customers
- Low-Value Repeat Customers
- One-Time High Spenders
- One-Time Medium Customers
- One-Time Low-Value Customers

**Preferred source and grain**

- Source: customer-level aggregates from `fact_customer_orders`
- Required output grain: one row per `customer_unique_id`

**Implementation status and caveat**

No segmentation thresholds or segmentation model are present in the current dbt
project. The names are governed, but the numerical thresholds are unavailable.
The AI must not invent thresholds or reproduce segment assignment until the
original implementation or documented thresholds are supplied.

## Cohort Analysis

**Business definition**

Customers are assigned to cohorts based on the month of their first purchase.
Subsequent purchases are measured with a monthly index representing the number
of months since the initial purchase. The output is used to analyze customer
purchasing and retention patterns over time.

**Preferred source and grain**

- Preferred output: `cohort_analysis`
- Underlying source: `fact_customer_orders`
- Output grain: one row per (`cohort_month`, `month_index`)

**Formula components**

```text
Cohort Month = month of first purchase
Month Index = months between first purchase and purchase activity
Retention Rate = active distinct customers / month-zero cohort customers
```

**Status scope**

The business definition does not explicitly identify a status filter. The
current model includes all item-bearing order statuses. This is an unresolved
implementation assumption.

**Caveats**

- The model counts distinct customers active in each month index. It is an
  activity-cohort table, not a continuous survival curve; customers can skip a
  month and return later.
- Month differences count month boundaries.
- Multiple purchases by one customer in the same cell count once.

**Validated reference values**

- Cohorts: **23**
- Output rows: **220**
- Cohort range: **2016-09 through 2018-08**
- Every cohort has month-zero retention equal to **1.0000**

## Product Analytics

Product analysis operates at order-item grain using `fact_order_items`, joined
to `dim_products` on the unique `product_id` when product attributes or category
names are required.

### Product Revenue

**Business definition and formula**

```sql
Product Revenue = sum(price)
```

Calculate at product or product-category grain as requested.

**Status scope**

No default status filter is specified by the business definition. The AI must
not silently choose all-status or delivered-only product revenue. The requested
scope must be stated or clarified.

**Caveats**

- Freight is excluded.
- Preserve the null English-category group unless an explicit presentation label
  is applied.
- Do not use `fact_customer_orders.order_value` after joining to item grain; it
  would repeat once per item.

### Units Sold

**Business definition and formula**

```sql
Units Sold = count(order_item_id)
```

**Required grain:** Order-item grain, grouped by product or category as needed.

**Status scope:** Not specified; it must be made explicit for the analysis.

### Average Selling Price (ASP)

**Business definition and formula**

```text
ASP = Product Revenue / Units Sold
```

The numerator and denominator must use identical product, date, and status scope.
At the raw fact level, `avg(price)` is equivalent when each row represents one
item position.

## Seller Analytics

Seller analysis operates at order-item grain using `fact_order_items`, optionally
joined to `dim_sellers` on the unique `seller_id`.

### Seller Revenue

**Business definition and formula**

```sql
Seller Revenue = sum(price)
```

grouped by `seller_id`.

**Status scope**

No default status filter is specified. The analysis must state or clarify its
status scope.

**Caveats**

- Freight is separate and excluded.
- Do not aggregate seller revenue from `fact_customer_orders`; it has no seller
  identifier and joining order value to items would multiply it.

### Seller Contribution

**Business definition and formula**

```text
Seller Contribution = Seller Revenue / Total Marketplace Revenue
```

The seller numerator and marketplace denominator must use the same date, status,
and other analytical filters. The denominator must be based on item `price` at
order-item grain, not repeated order-level revenue.

## Fulfillment and Logistics

Fulfillment analysis operates at order grain using `fact_customer_orders`.
Lifecycle timestamp nulls are valid and must not be automatically imputed.

### Warehouse Processing Time

**Business definition and formula**

```text
Warehouse Processing Time = Carrier Pickup Date - Order Approval Date
```

Technical columns:

```text
order_delivered_carrier_date - order_approved_at
```

**Required rows and caveats**

- Both timestamps must be non-null for a duration to be calculated.
- Do not automatically remove negative or anomalous durations without an
  explicit data-quality rule.
- The business definition does not explicitly specify whether the population is
  delivered orders only; this scope remains ambiguous.

### Delivery Time

**Business definition and formula**

```text
Delivery Time = Customer Delivery Date - Purchase Date
```

**Required scope and caveats**

- "Successful delivery" implies delivered orders with a non-null customer
  delivery timestamp.
- `fact_customer_orders` contains purchase `full_date`, not the original purchase
  timestamp. It can support calendar-day delivery time but not exact elapsed
  timestamp duration. An exact timestamp implementation is not available from
  the current analytical fact and requires an approved model enhancement or the
  internal order staging timestamp.
- Valid null delivery timestamps must be preserved and excluded only when the
  duration mathematically requires both endpoints.

### Delivered Rate

**Business definition and formula**

```text
Delivered Rate = Delivered Orders / Total Orders
```

**Required grain:** One row per order.

**Implementation ambiguity**

`fact_customer_orders` excludes 775 source orders without items. Therefore,
"Total Orders" is ambiguous between all source orders and item-bearing analytical
orders. The governed denominator must be confirmed before publishing this metric.

Read-only diagnostics, not final governed reference values:

- All source orders: 99,441; delivered orders: 96,478; rate: **97.0203%**
- Item-bearing fact orders: 98,666; delivered item-bearing orders: 96,478;
  rate: **97.7824%**

The AI must not select one denominator silently.

## Validated reference snapshot

These values validate the current DuckDB migration and implementation scope.
They are not substitutes for the governed definitions above.

| Reference | Value |
|---|---:|
| Total item-bearing customers | 95,420 |
| One-time customers | 92,507 |
| Repeat customers | 2,913 |
| Repeat Purchase Rate | 3.0528% |
| Retained within 90 days | 1,992 |
| Overall 90-day retention | 2.0876% |
| One-time average historical CLTV | 138.67 |
| Repeat average historical CLTV | 262.03 |
| Total item-bearing `order_value`, all statuses | 13,591,643.70 |
| Delivered item-bearing orders | 96,478 |
| Delivered revenue | 13,221,498.11 |
| Delivered AOV | 137.04 |

The all-status `order_value` value **must not** be presented as delivered revenue.

## Known definition-to-implementation gaps

1. Repeat Purchase Rate, Customer Retention, CLTV, and Cohort Analysis do not have
   an explicitly governed order-status filter. Current dbt behavior uses all
   item-bearing statuses.
2. Product Revenue, Units Sold, ASP, Seller Revenue, and Seller Contribution do
   not have a governed default status scope. The agent must clarify or explicitly
   state the chosen scope.
3. Customer segmentation names are governed, but thresholds and an executable
   implementation are absent.
4. Delivered Rate has two plausible denominators because the analytical order
   fact excludes 775 source orders without items.
5. Exact timestamp-level Delivery Time cannot be reproduced from
   `fact_customer_orders` because it retains purchase date rather than purchase
   timestamp.
6. Warehouse Processing Time has the required timestamps, but its governed
   population/status scope is not explicit.
