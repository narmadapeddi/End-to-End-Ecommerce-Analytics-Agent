# Olist Analytics Data Catalog

This catalog describes the analytical relations currently materialized in the
`main` schema of `database/olist.duckdb`. It is based on the dbt SQL and the
validated DuckDB relations, not on assumptions about the original CSV files.

The AI analytics agent should prefer the fact, dimension, and analytics tables
documented here. The six `STG_*` models are internal transformation inputs and
normally should not be queried for business analysis.

**Business-definition authority:** This catalog describes table structure, grain, relationships, and safe usage. It does not define business metrics. For metric definitions, formulas, status scope, and business assumptions, `docs/metrics.md` is authoritative.

## Grain rules

- Use **order grain** for customer, order, revenue, AOV, status, and fulfillment
  questions. The primary table is `fact_customer_orders`.
- Use **item grain** for product, product-category, seller, item-price, and
  item-level freight questions. The primary table is `fact_order_items`.
- Never treat a row in `fact_order_items` as an order. Use
  `count(distinct order_id)` when counting orders from item grain.
- When joining item grain to an order-grain table, the result remains item grain.
  Do not sum an order-level measure after that join unless it is first protected
  from repetition or re-aggregated at order grain.
- Candidate keys below are validated logical keys. DuckDB does not currently
  enforce them as primary-key constraints.

## Relationship map

```text
dim_date (full_date) 1 ──────── * fact_customer_orders (full_date)
       │
       └─────────────────────── * fact_order_items (full_date)

fact_customer_orders (order_id) 1 ───── * fact_order_items (order_id)

dim_products (product_id) 1 ──────────── * fact_order_items (product_id)

dim_sellers (seller_id) 1 ────────────── * fact_order_items (seller_id)

fact_customer_orders (customer_unique_id) * ── logical customer identity
fact_order_items     (customer_unique_id) * ── logical customer identity

dim_customers is keyed by customer_id, not customer_unique_id.
```

All current `fact_order_items.product_id` values match `dim_products`, all
current `fact_order_items.seller_id` values match `dim_sellers`, and fact dates
match `dim_date`.

There is no safe direct geography join from either fact to `dim_customers` in
the current analytical layer. The facts contain `customer_unique_id`, while
`dim_customers` is uniquely keyed by `customer_id`. Because
`customer_unique_id` occurs more than once in `dim_customers`, joining on it can
multiply fact rows. Geographic analysis at fact grain requires a curated bridge
or an order-to-`customer_id` relationship; it must not use a naive
`customer_unique_id` join.

## Fact tables

### `fact_customer_orders`

**Purpose:** Order-level analysis of customers, order status, purchase date,
fulfillment timestamps, item revenue, and freight.

- **Validated rows:** 98,666
- **Grain:** One row per item-bearing customer order.
- **Candidate key:** `order_id` (98,666 distinct, zero nulls).
- **Important columns:**
  - `order_id`: Unique order identifier.
  - `customer_unique_id`: Cross-order customer identity used for customer
    counts, repeat behavior, retention, and CLTV.
  - `order_status`: Raw order lifecycle status. No status filter is applied.
  - `full_date`: Purchase date derived from `order_purchase_timestamp`.
  - `order_approved_at`, `order_delivered_carrier_date`,
    `order_delivered_customer_date`, `order_estimated_delivery_date`:
    fulfillment lifecycle timestamps; valid lifecycle nulls are preserved.
  - `order_value`: Sum of item `price` for the order. It excludes freight.
  - `freight_value`: Sum of item-level freight for the order.
- **Relationships:**
  - Many orders to one `dim_date` row through `full_date`.
  - One order to many `fact_order_items` rows through `order_id`.
  - `customer_unique_id` is a customer identity, but it is not a safe unique
    join key to `dim_customers`.
- **Use for:** Revenue, freight, AOV, order counts, status analysis, customer
  counts, repeat purchasing, order-level fulfillment, and customer CLTV.
- **Caveats:**
  - The model uses an inner join to order items. Exactly 775 source orders with
    no items are excluded.
  - All item-bearing statuses are included, including canceled and unavailable
    orders. Apply an explicit status filter only when the business question
    requires one, and state the chosen scope.
  - `order_value` excludes freight. Do not call `order_value + freight_value`
    revenue unless that combined definition is explicitly requested.
  - Monetary columns are `DOUBLE`; small floating-point differences can appear
    when aggregations are performed in different orders.
  - The table has purchase date but not purchase timestamp, so intraday purchase
    analysis is not available here.

### `fact_order_items`

**Purpose:** Item-level analysis by product, category, seller, customer, order
status, and purchase date.

- **Validated rows:** 112,650
- **Grain:** One row per item position within an order.
- **Composite candidate key:** (`order_id`, `order_item_id`) with zero duplicate
  key groups and zero nulls.
- **Important columns:**
  - `order_id`: Parent order.
  - `order_item_id`: Sequential item position within the order.
  - `product_id`: Safe many-to-one join to `dim_products`.
  - `seller_id`: Safe many-to-one join to `dim_sellers`.
  - `customer_unique_id`: Cross-order customer identity.
  - `order_status`: Raw parent-order status; no status filter is applied.
  - `full_date`: Parent order purchase date.
  - `price`: Item price.
  - `freight_value`: Item-level freight.
- **Relationships:**
  - Many items to one `fact_customer_orders` row through `order_id`.
  - Many items to one product, seller, and date through their documented keys.
- **Use for:** Product sales, category sales, seller sales, item counts, product
  mix, item price, and item-level freight.
- **Caveats:**
  - This is not order grain. `count(*)` counts item positions, not orders.
  - Product and seller analysis should start here because those identifiers are
    not present in `fact_customer_orders`.
  - Summing `price` produces item-price revenue at the selected item scope.
    Summing `freight_value` produces freight, not item revenue.
  - Joining to `fact_customer_orders` repeats order-level fields once per item.
    Never sum repeated `order_value` after this join.
  - Monetary columns are `DOUBLE` and can exhibit small floating-point artifacts.
  - `shipping_limit_date` exists in staging but is not included in this fact.

## Dimensions

### `dim_customers`

**Purpose:** Maps order-level customer records to persistent customer identity
and customer location attributes.

- **Validated rows:** 99,441
- **Grain:** One row per `customer_id`.
- **Candidate key:** `customer_id` (99,441 distinct, zero nulls).
- **Important columns:** `customer_id`, `customer_unique_id`, `zip_code`, `city`,
  and `state`.
- **Relationships:** A persistent customer can have multiple order-level
  customer records. There are 96,096 distinct `customer_unique_id` values across
  99,441 rows.
- **Use for:** Inspecting customer identity mapping and location attributes when
  a safe `customer_id` relationship is available.
- **Caveats:**
  - `customer_unique_id` is not unique.
  - Joining either fact directly to this table on `customer_unique_id` can
    multiply rows and inflate counts and monetary values.
  - The current facts do not expose `customer_id`; therefore customer geography
    cannot be safely attached to them with the available analytical tables alone.
  - `zip_code` is text so leading zeros are preserved.

### `dim_products`

**Purpose:** Product attributes and Portuguese-to-English category enrichment.

- **Validated rows:** 32,951
- **Grain:** One row per product.
- **Candidate key:** `product_id` (32,951 distinct, zero nulls).
- **Important columns:** `product_id`, `product_category_name`,
  `product_category_name_english`, name and description lengths, photo count,
  weight, length, height, and width.
- **Relationships:** One product to many `fact_order_items` rows through
  `product_id`.
- **Use for:** Product and category analysis when joined to item grain.
- **Caveats:**
  - 623 products have null `product_category_name_english`: 610 have no source
    category and 13 belong to source categories absent from the translation file.
  - A left join created this dimension, so untranslated products are retained.
  - Do not silently discard the null category group. Label it for presentation
    only when the response makes that treatment explicit.
  - Physical measure names omit units, but the underlying source values remain
    grams for weight and centimeters for dimensions.

### `dim_sellers`

**Purpose:** Seller identity and location attributes.

- **Validated rows:** 3,095
- **Grain:** One row per seller.
- **Candidate key:** `seller_id` (3,095 distinct, zero nulls).
- **Important columns:** `seller_id`, `seller_city`, `seller_state`, and
  `seller_zip_code_prefix`.
- **Relationships:** One seller to many `fact_order_items` rows through
  `seller_id`.
- **Use for:** Seller performance and seller geography analysis at item grain.
- **Caveats:**
  - Seller analysis should use `fact_order_items`; the order fact has no
    `seller_id`.
  - Seller city values are intentionally unstandardized and include source
    spelling and formatting variants.
  - ZIP prefixes are text and retain leading zeros.

### `dim_date`

**Purpose:** Calendar attributes for purchase-date analysis.

- **Validated rows:** 4,018
- **Grain:** One row per calendar date.
- **Candidate key:** `full_date` (4,018 distinct, zero nulls).
- **Coverage:** 2015-01-01 through 2025-12-31 with no gaps.
- **Important columns:** `full_date`, `year`, `quarter`, `month`, `month_name`,
  `week_of_year`, `day`, `day_name`, and `is_weekend`.
- **Relationships:** One date to many rows in each fact through `full_date`.
- **Use for:** Purchase-date filtering, grouping, and calendar attributes.
- **Caveats:**
  - Fact `full_date` represents purchase date, not approval or delivery date.
  - Week numbering follows DuckDB's `week()` behavior. Confirm the intended week
    convention before making cross-system week-number comparisons.

## Analytics tables

### `cohort_analysis`

**Purpose:** Monthly purchase-cohort activity and retention rates.

- **Validated rows:** 220
- **Grain:** One row per (`cohort_month`, `month_index`).
- **Composite candidate key:** (`cohort_month`, `month_index`) (220 unique pairs).
- **Important columns:**
  - `cohort_month`: Customer's first item-bearing purchase month, formatted
    `YYYY-MM`.
  - `month_index`: Month boundaries since the first purchase date.
  - `customer_count`: Distinct customers active at that month index.
  - `customer_month0_count`: Initial cohort size.
  - `retention_rate`: `customer_count / customer_month0_count`, rounded to four
    decimal places.
- **Dependencies:** `fact_customer_orders`.
- **Use for:** Standard monthly cohort tables and retention heatmaps using the
  existing project definition.
- **Caveats:**
  - This measures activity in each month index, not continuous survival. Rates
    can rise after falling because customers may skip a month and return later.
  - All item-bearing order statuses are included.
  - Multiple orders by one customer in the same cohort/month cell count once.

### `customer_retention_analysis`

**Purpose:** Customer-level classification based on time from first to second
item-bearing purchase date.

- **Validated rows:** 95,420
- **Grain:** One row per `customer_unique_id`.
- **Candidate key:** `customer_unique_id` (95,420 distinct, zero nulls).
- **Important columns:** `customer_unique_id`, `first_purchase`,
  `second_purchase`, and `retained_flag`.
- **Dependencies:** `fact_customer_orders`.
- **Use for:** The project's governed 90-day retained/not-retained classification.
- **Caveats:**
  - `Retained` means a non-null second purchase no more than 90 calendar days
    after the first; day 90 is included.
  - Repeat customers whose second purchase is after 90 days are `Not Retained`.
  - Purchases are ordered by date rather than timestamp, so same-day repeat
    purchases have a zero-day difference.
  - All item-bearing order statuses are included.
  - `day_difference` is calculated internally but is not exposed in the output.

### `product_cltv_analysis`

**Purpose:** Average total customer lifetime order value for customers associated
with each English product category.

- **Validated rows:** 72
- **Grain:** One row per `product_category_name_english` grouping value, including
  one null group.
- **Grouping key:** `product_category_name_english`. It is not a strict candidate
  key because one output row has a null value; there are 71 distinct non-null
  category values plus the null group.
- **Important columns:** `product_category_name_english` and `avg_cltv`.
- **Dependencies:** `fact_customer_orders`, `fact_order_items`, and
  `dim_products`.
- **Use for:** Comparing the average total CLTV of customers who have purchased
  from different product categories.
- **Caveats:**
  - This is not revenue generated within a category. Each customer's full CLTV
    is associated with every distinct category that customer purchased.
  - A customer contributes once per category because the model deduplicates
    (`customer_unique_id`, category) pairs.
  - The null English-category group is retained.
  - `avg_cltv` inherits `DOUBLE` floating-point behavior from `order_value`.
  - Freight is excluded from CLTV.

## Internal staging models

The following dbt models load and minimally adapt the six raw CSV inputs:

- `STG_CUSTOMERS`
- `STG_PRODUCTS`
- `STG_SELLERS`
- `STG_ORDERS`
- `STG_ORDER_ITEMS`
- `STG_CATEGORY_NAME_TRANSLATION`

They preserve source-level data and provide the contracts used by dimensions and
facts. They are internal transformation models, not the default interface for
business questions. The AI should query them only for source reconciliation,
data-quality investigation, or a question that cannot be answered from the
documented analytical layer.

## Question-to-table routing

| Business question | Preferred table(s) | Required grain note |
|---|---|---|
| Revenue, freight, AOV, or order count | `fact_customer_orders` | One row per item-bearing order |
| Order status or order-level fulfillment | `fact_customer_orders` | Lifecycle timestamps may be null |
| Customer count, repeat behavior, or customer CLTV | `fact_customer_orders` | Use `customer_unique_id` |
| Product or category performance | `fact_order_items` + `dim_products` | Remain at item grain or aggregate deliberately |
| Seller performance or seller geography | `fact_order_items` + `dim_sellers` | Seller analysis is item-grain analysis |
| Item price or item freight | `fact_order_items` | `count(*)` counts item positions |
| Calendar grouping of facts | Either fact + `dim_date` | Join on `full_date` |
| Monthly cohort retention | `cohort_analysis` | One row per cohort and month index |
| Customer-level 90-day retention | `customer_retention_analysis` | One row per customer |
| Category-associated average CLTV | `product_cltv_analysis` | Not category-specific revenue |
| Customer geography tied to orders or revenue | Not safely available from the current analytical tables | Do not join facts to `dim_customers` on `customer_unique_id`; a bridge or fact key is needed |

## Safe-join checklist for the AI

Before issuing a query:

1. State the intended output grain.
2. Start from the fact table matching that grain.
3. Join dimensions only on their validated candidate keys.
4. Treat `fact_customer_orders` to `fact_order_items` as one-to-many.
5. After any item-grain join, use `count(distinct order_id)` for order counts.
6. Never sum repeated `fact_customer_orders.order_value` at item grain.
7. Do not join `dim_customers` to a fact on `customer_unique_id`.
8. State the order-status scope and whether freight is included.
9. Preserve or explicitly label null English product categories.
