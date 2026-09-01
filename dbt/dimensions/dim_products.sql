{{ config(materialized='table') }}

SELECT
p.product_id,
p.product_category_name,
t.product_category_name_english,
p.product_name_length,
p.product_description_length,
p.product_photos_qty,
p.product_weight,
p.product_length,
p.product_height,
p.product_width
    
FROM {{ ref('STG_PRODUCTS') }} p
LEFT JOIN {{ ref('STG_CATEGORY_NAME_TRANSLATION') }} t
    ON p.product_category_name = t.product_category_name
