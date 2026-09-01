# Source Data

This project uses the Brazilian E-Commerce Public Dataset by Olist.

The original dataset contains multiple CSV files covering customers, orders, order items, products, sellers, payments, reviews, geolocation, and product category translations.

## Source Files Used

The local project contains the following source datasets:

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

## Project Usage

The raw source files are loaded locally and transformed through dbt into staging, dimension, fact, and analytical models.

The AI analytics agent does not query the raw CSV files directly. It queries the modeled DuckDB analytical layer.

## Data Availability

The raw CSV files are not duplicated in this repository.

The dataset is publicly available on Kaggle as the **Brazilian E-Commerce Public Dataset by Olist**.
