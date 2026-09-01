# AI Analytics Agent Operating Policy

## Authority and precedence

- `docs/metrics.md` is authoritative for governed business definitions,
  formulas, status scope, assumptions, caveats, and documented ambiguities.
- `docs/data_catalog.md` is authoritative for table purpose, structure, grain,
  candidate keys, relationships, safe joins, and table selection.
- Do not redefine, override, or infer a replacement for anything governed by
  those documents.
- When a business definition and a technical implementation differ, preserve the
  documented business definition and disclose the implementation limitation.

## Required workflow

```text
Understand
→ Ground
→ Determine grain
→ Plan
→ Generate SQL
→ Execute
→ Inspect result
→ Validate
→ Revise if necessary
→ Explain
```

1. **Understand:** Identify the business question, requested output, time period,
   dimensions, and decision the result should support.
2. **Ground:** Read the relevant sections of `docs/metrics.md` and
   `docs/data_catalog.md`. For a governed metric, read its definition before
   calculating it.
3. **Determine grain:** State the required analytical and output grain before
   choosing tables.
4. **Plan:** Select tables, joins, filters, status scope, aggregation, and an
   appropriate validation check.
5. **Generate SQL:** Write DuckDB-compatible, read-only SQL.
6. **Execute:** Run only the queries needed to answer and support the question.
7. **Inspect result:** Check returned rows, nulls, types, magnitudes, boundaries,
   and whether the result matches the requested grain.
8. **Validate:** When useful, perform a reconciliation, second calculation,
   distinct count, row-count check, boundary check, or known-reference check.
9. **Revise if necessary:** If inspection or validation fails, diagnose the
   cause, correct the query, execute it again, and revalidate. Do not present a
   failed or uninspected first result.
10. **Explain:** Give the direct business answer and disclose the definition,
    grain, scope, SQL, material caveats, and relevant validation.

## Grounding and ambiguity rules

- Never silently redefine a governed metric.
- Never silently resolve an ambiguity documented in `docs/metrics.md`.
- Apply status filters exactly as governed in `docs/metrics.md`.
- If the user supplies a scope that resolves a documented ambiguity, use it and
  state it explicitly.
- If an unresolved ambiguity would materially change the result or its business
  meaning, stop before calculation and ask the user for clarification.
- If an ambiguity does not materially affect the requested result, it may be
  disclosed without blocking, but it must not be hidden.
- Do not present a technical implementation assumption as a governed business
  rule.
- Do not invent missing segmentation thresholds, metric rules, status scopes, or
  denominator definitions.

## Grain, table, and join rules

- Determine grain before selecting tables or aggregations.
- Select tables according to `docs/data_catalog.md`.
- Prefer analytical facts, dimensions, and precomputed analytics tables over
  `STG_*` models. Use staging only for justified source reconciliation or
  data-quality investigation described by the catalog.
- Use `customer_unique_id` for customer-level analysis.
- Never count item rows as orders. At item grain, count orders with
  `count(distinct order_id)`.
- Protect every calculation from one-to-many join multiplication.
- Do not join either fact to `dim_customers` using `customer_unique_id`.
- Do not sum order-level `order_value` after it has been repeated across item
  rows.
- Keep numerator and denominator filters, dates, populations, and status scope
  consistent.
- Use order grain for customer, order, and fulfillment analysis.
- Use item grain for product and seller analysis.
- Keep freight separate from product revenue unless the user explicitly requests
  a combined amount and the response labels it accurately.
- Preserve valid null and unknown categories. A presentation label may be added
  only when stated explicitly; do not silently filter or rewrite the underlying
  category.

## SQL and execution safety

- Generate DuckDB-compatible, read-only SQL only.
- Use `SELECT`, read-only CTEs, and read-only inspection or validation queries.
- Do not issue `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY`, `ALTER`,
  `DROP`, `TRUNCATE`, `ATTACH`, or other state-changing statements.
- While answering an analytical question, never modify the DuckDB database, dbt
  models, source CSVs, documentation, or other project files.
- Query only the data needed for the requested analysis and its proportionate
  validation.

## Result inspection and validation

- Inspect query results before presenting them.
- Confirm that output row count and uniqueness match the intended grain when
  those checks are material.
- Check important nulls, join coverage, filter scope, and aggregation boundaries.
- Reconcile totals before and after joins when multiplication or row loss is a
  realistic risk.
- Use known reference values in `docs/metrics.md` when they provide a relevant
  reasonableness check; do not force an unrelated reference comparison.
- For threshold metrics, check important boundary behavior when relevant.
- If validation fails, diagnose and revise the SQL, execute the corrected query,
  and validate again before answering.
- Do not run unnecessary validation queries when the result is already
  sufficiently supported. Validation should be proportional to the risk and
  importance of the claim.

## Exploratory analysis

For a question that is not a predefined governed metric:

- Investigate it using the documented analytical model.
- Determine and state the analytical grain.
- Use documented tables and safe joins.
- State filters and status scope rather than implying they are governed.
- Validate important findings proportionately.
- Clearly label the result as a derived finding, not a governed metric.
- Do not create a new governed definition merely because a calculation is useful.

## Required response contract

For each completed analysis, return:

1. **Direct business answer**
2. **Metric/business definition used** — or identify the result as exploratory
3. **Tables and analytical grain used**
4. **Filters and status scope**
5. **SQL executed**
6. **Material caveats or unresolved assumptions**
7. **Validation performed**, when relevant

Keep the explanation concise and decision-oriented. Do not hide material
uncertainty, but do not burden the response with irrelevant implementation
detail.

## Excluded capabilities

Do not add or invoke web browsing, vector databases, embeddings, RAG frameworks,
database writes, autonomous file modification, or unnecessary agent frameworks
as part of analytical question answering.
