# dbt Analytics Models

This folder contains the dbt transformation layer used to build the analytical models queried by the AI analytics agent.

The models transform the Olist source data into staging, dimensional, fact, and analytical tables while preserving documented grain and business logic.

## Model Layers

### Staging

The staging models clean and standardize the source datasets while preserving the original business records.

Models include:

- `stg_customers`
- `stg_products`
- `stg_sellers`
- `stg_orders`
- `stg_order_items`
- `stg_category_name_translation`

### Dimensions

Reusable descriptive entities:

- `dim_customers`
- `dim_products`
- `dim_sellers`
- `dim_date`

### Facts

Core analytical fact tables:

- `fact_customer_orders` — one row per item-bearing order
- `fact_order_items` — one row per order item

Separating the two fact tables prevents order-level and item-level metrics from being mixed incorrectly.

### Analytics

Business-analysis models built on top of the transformed data:

- `cohort_analysis`
- `customer_retention_analysis`
- `product_cltv_analysis`

## Role in the AI Agent

The AI agent queries these modeled analytical tables rather than operating directly on raw CSV files.

This allows the agent to work with documented table grains, relationships, and business logic before generating and executing analytical SQL.
