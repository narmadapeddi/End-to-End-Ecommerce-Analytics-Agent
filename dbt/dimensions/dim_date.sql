{{ config(materialized='table') }}

with calendar as (

    select
        date '2015-01-01' + cast(day_offset as integer) as full_date

    from range(4018) as t(day_offset)

)

select

    full_date,

    year(full_date) as year,

    quarter(full_date) as quarter,

    month(full_date) as month,

    monthname(full_date) as month_name,

    week(full_date) as week_of_year,

    day(full_date) as day,

    dayname(full_date) as day_name,

    case
        when isodow(full_date) in (6,7)
        then true
        else false
    end as is_weekend

from calendar
