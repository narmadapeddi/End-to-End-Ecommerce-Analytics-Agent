# DuckDB Analytical Database

This project uses DuckDB as the local analytical database queried by the AI analytics agent.

The database is built from the Olist source data and transformed through the project's dbt models into staging, dimension, fact, and analytical layers.

## Role in the Agent

DuckDB provides the execution layer for analytical SQL generated or constructed by the agent.

The workflow is:

Business Question  
→ AI Agent  
→ SQL Generation / Construction  
→ Read-Only Database Tool  
→ DuckDB  
→ Query Result  
→ Validation  
→ Business Explanation

The agent connects to DuckDB through `agent/database_tool.py`, which enforces read-only query execution and blocks destructive database operations.

## Local Database

The generated `olist.duckdb` database file is not stored in this repository.

It can be recreated locally using the source data and dbt transformation models included in the project.
