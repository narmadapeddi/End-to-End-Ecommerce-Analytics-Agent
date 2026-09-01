{{ config(materialized='table') }}

select
    product_id,
    product_category_name,
    cast(product_name_lenght as bigint) as product_name_length,
    cast(product_description_lenght as bigint) as product_description_length,
    cast(product_photos_qty as bigint) as product_photos_qty,
    cast(product_weight_g as bigint) as product_weight,
    cast(product_length_cm as bigint) as product_length,
    cast(product_height_cm as bigint) as product_height,
    cast(product_width_cm as bigint) as product_width
from {{ source('raw', 'olist_products') }}
