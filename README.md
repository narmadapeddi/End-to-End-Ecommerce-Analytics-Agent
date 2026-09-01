## 🤖 End-to-End E-commerce Analytics Agent

A local analytics agent built on my e-commerce dimensional model to answer business questions using governed metrics, validated SQL, and practical guardrails.

![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=flat-square&logo=duckdb&logoColor=000000)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=flat-square&logo=ollama&logoColor=FFFFFF)
![Qwen3:1.7B](https://img.shields.io/badge/Qwen3%3A1.7B-6C5CE7?style=flat-square)
![Local LLM](https://img.shields.io/badge/Local_LLM-2D3436?style=flat-square)
![Agentic Analytics](https://img.shields.io/badge/Agentic_Analytics-8E44AD?style=flat-square)
![SQL Guardrails](https://img.shields.io/badge/SQL_Guardrails-2980B9?style=flat-square)
![Read--Only Execution](https://img.shields.io/badge/Read--Only_Execution-27AE60?style=flat-square)

> This repository extends the [End-to-End E-commerce Analytics](https://github.com/narmadapeddi/End-to-End-Ecommerce-Analytics) project. The original project established the dimensional models and business metrics; this extension adds governed analytical Q&A on top of that foundation.

---

## 📖 Project Overview

The original Olist project transformed raw e-commerce data into validated fact and dimension models for customer, product, seller, and fulfillment analysis.

This project extends that foundation with a local analytics agent that can:

- Interpret natural-language business questions
- Read relevant metric and data-model context
- Select the appropriate tables and grain
- Ask for clarification when a question is ambiguous
- Generate SQL for straightforward questions
- Construct complex SQL deterministically when needed
- Execute read-only queries in DuckDB
- Validate query structure, grain, and results
- Revise after an error or failed validation
- Explain findings in business terms
- Block analytically unsafe or destructive requests

The agent focuses on analytical Q&A. It does not generate dashboards or visualizations.

---

## 🎯 Why I Built This

The original Olist platform answered predefined business questions through SQL analysis and Power BI dashboards. New questions still required manually selecting the correct tables, choosing the appropriate grain and metrics, writing SQL, validating the output, and explaining the result.

I built this extension to make that process more flexible while preserving the analytical rules that made the original project reliable.

The goal was not to allow an LLM to query data freely. The goal was to combine model reasoning with data-model grounding, deterministic query construction, validation, clarification, and safety controls.

---

## 🏗 Project at a Glance

| | |
|---|---|
| **Objective** | Extend the Olist dimensional model with governed analytical Q&A |
| **My Role** | Agent workflow, grounding, SQL execution, guardrails, and model evaluation |
| **Technology** | DuckDB, Ollama API, Qwen3, Llama 3.2, Qwen2.5 |
| **Outcome** | Local analytics agent validated across seven analytical and safety scenarios |

---

## 🌟Existing Analytics Foundation

The agent does not query raw CSV files without context. It builds on the analytical foundation established in the original Olist project.

### Validated Data

Source records were checked for duplicates, nulls, keys, grain, and table relationships before analysis.

### Defined Grain

Each model clearly defines what one row represents, allowing the agent to choose the correct level of detail.

### Dimensional Models

Fact and dimension models support customer, product, seller, and fulfillment analysis.

### Governed Metrics

Business metrics such as average order value, revenue, repeat-purchase rate, and CLTV have consistent definitions and scope rules.

---

## 🔁 Agent Workflow

The agent follows a controlled analytical loop:

```text
Business Question
        ↓
Interpret the Request
        ↓
Apply Metric and Data-Model Grounding
        ↓
Select the Correct Tables and Grain
        ↓
Plan the Analytical Approach
        ↓
Generate or Deterministically Construct SQL
        ↓
Execute Read-Only SQL in DuckDB
        ↓
Validate the Query and Results
        ↓
Explain the Finding
```

The workflow can branch when a request cannot safely continue:

```text
Ambiguous Question  → Ask for Clarification
Grain Mismatch      → Block or Reframe
Unsafe SQL          → Block
Invalid Result      → Revise
```

---

## ✅ Grounding

Grounding gives the agent the context needed to interpret the modeled data correctly.

### Data-Model Context

Identifies the available tables, relationships, and grain of each model.

### Metric Definitions

Applies consistent definitions for AOV, CLTV, revenue, and repeat-purchase rate.

### Scope Rules

Determines which orders, customers, statuses, and filters belong in the requested analysis.

### Question Context

Identifies the requested metric, dimensions, filters, and expected output.

---

## 🔍 Guardrails

A query can execute successfully and still produce a misleading analytical result. The following controls reduce that risk.

### Ambiguity Detection

The agent requests clarification when a question has multiple valid interpretations.

### Grain Validation

The agent checks whether the requested metric and dimensions can be combined at a valid level of detail.

### Deterministic SQL Construction

Structurally sensitive analysis does not depend entirely on LLM-generated SQL.

### Read-Only Execution

Queries run through a read-only DuckDB layer that blocks destructive operations.

### Result Validation

The agent checks the query structure and returned output before explaining the result.

The model supports interpretation and planning, but analytical rules determine whether a request can proceed safely.

---

## ✍🏻 Local Model Evaluation

Four local models were evaluated through practical analytics tasks:

- **Qwen3:4B**
- **Qwen3:1.7B**
- **Llama 3.2:3B**
- **Qwen2.5:3B-Instruct**

This was a task-based evaluation rather than a formal machine-learning benchmark.

### Evaluation Criteria

- **Speed:** Time required to make the first useful decision
- **Protocol Following:** Ability to follow the required query-and-answer structure
- **Analytical Correctness:** Understanding of metric definitions, grain, and scope
- **Complex-Query Completion:** Ability to finish multi-stage analysis

### Qwen3:1.7B — Selected Model

Qwen3:1.7B provided the best speed-to-capability balance for local use.

During the customer-count test:

- First decision: **12.23 seconds**
- Total response: **23.32 seconds**

It became the final default model.

### Qwen3:4B

The larger model showed stronger capacity but was too slow locally. Even after reducing the grounding context from approximately 40K to 13K characters, some first decisions took more than 90 seconds.

### Llama 3.2:3B

The model understood parts of the multi-stage CLTV analysis but took approximately 90 seconds for its first decision. It calculated customer-level CLTV but did not complete the final repeat-versus-one-time comparison.

### Qwen2.5:3B-Instruct

The model recognized parts of the CLTV structure and customer classification but did not consistently complete the final aggregation or required response protocol.

> Timings were observed during practical local tests. Tasks and conditions varied, so the results should not be interpreted as a standardized model benchmark.

---

## 🚀 Test Scenarios and Results

The final workflow was tested across seven analytical and safety scenarios.

### 1. Customer Count

The agent selected the appropriate modeled data and returned **95,420 item-bearing customers**.

### 2. Delivered Average Order Value

The agent applied the governed delivered-order definition and calculated an AOV of approximately **$137.04**.

### 3. Repeat-Purchase Rate

The original question did not define which order statuses should count toward a purchase.

The agent asked whether the calculation should include all orders or only delivered orders. After the delivered-order scope was confirmed, it calculated the percentage of customers with more than one delivered order and returned a repeat-purchase rate of approximately **3.00%**.

### 4. CLTV Comparison

The agent completed a multi-stage workflow to:

1. Calculate customer-level CLTV
2. Classify repeat and one-time customers
3. Aggregate the results by customer type
4. Compare the two groups

Results:

- Repeat customers: approximately **$262.03 average CLTV**
- One-time customers: approximately **$138.67 average CLTV**

### 5. AOV by Product Category

The agent blocked the request because AOV is defined at the order grain while product category exists at the item grain. Calculating it directly would have produced a misleading metric.

### 6. Seller Revenue

The agent rejected an overall revenue total when seller-level output was requested and returned a seller-grain result covering **3,095 sellers**.

### 7. Destructive SQL

The read-only database layer blocked destructive SQL and prevented modifications to the analytical data.

---

## 🏅 What Success Meant

A successful result was not always a number.

Depending on the question, the correct behavior could be to:

- Return a validated analytical answer
- Ask for clarification
- Enforce the requested output grain
- Reframe an unsafe request
- Revise a failed query
- Block a destructive operation

---

## 🔧 Key Design Decision

Testing showed that a larger model did not automatically create a more reliable analytical workflow.

Instead of depending on a larger LLM to generate every complex query, I selected the faster Qwen3:1.7B and combined it with:

- Data-model grounding
- Governed metric definitions
- Deterministic query construction
- Grain and ambiguity checks
- Read-only SQL execution
- Result validation

---

## 🚫 Limitations

- The agent was evaluated with seven representative scenarios rather than a large formal benchmark.
- It answers analytical questions but does not create charts or dashboards.
- Power BI remains the visualization layer in the original project.
- The system currently runs locally through DuckDB and Ollama.
- It does not include production features such as authentication, shared access, monitoring, or automated evaluation at scale.
- New datasets and business domains would require additional grounding, testing, and guardrails.

---

## 📒 Repository Structure

```text
end-to-end-ecommerce-analytics-agent/
├── README.md
│── .gitignore
│
├── agent/
│   ├── README.md
│   ├── analytics_agent.py
│   ├── database_tool.py
│   ├── llm_client.py
│   └── instructions.md
│
├── dbt/
│   ├── README.md
│   ├── dbt_project.yml
│   └── models/
│       ├── staging/
│       ├── dimensions/
│       ├── facts/
│       └── analytics/
│
├── docs/
│   ├── ai_agent.md
│   ├── data_catalog.md
│   └── metrics.md
│
├── database/
│   └── README.md
│
└── data/
    └── README.md
```
---
##  🖥️  Running the Project Locally

The AI analytics agent runs locally using **Python, Ollama, Qwen, DuckDB, and dbt**.

The local workflow is:

```text
Olist CSV Data
      ↓
     dbt
      ↓
DuckDB Analytical Models
      ↓
AI Analytics Agent
      ↓
Local Qwen LLM via Ollama
      ↓
SQL Generation / Tool Execution
      ↓
DuckDB Results
      ↓
Validation
      ↓
Business Answer
```

### Prerequisites

Before running the project, install:

- Python 3
- Ollama
- dbt Core
- dbt-duckdb
- DuckDB

The project was developed using a local Ollama model, so no external LLM API key is required.

---

### 1. Clone the Repository

Clone the project and move into the project directory:

```bash
git clone <YOUR_REPOSITORY_URL>
cd end-to-end-ecommerce-analytics-agent
```

---

### 2. Create a Python Virtual Environment

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it on macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

Install the required Python packages:

```bash
pip install duckdb dbt-core dbt-duckdb
```

---

### 3. Install and Start Ollama

Install Ollama on your machine if it is not already installed.

The final agent uses **Qwen3:1.7B** as the local LLM.

Download the model:

```bash
ollama pull qwen3:1.7b
```

Verify that the model is available:

```bash
ollama list
```

Make sure Ollama is running before starting the analytics agent.

The agent communicates with the local Ollama service through `agent/llm_client.py`.

---

### 4. Download the Olist Dataset

This project uses the **Brazilian E-Commerce Public Dataset by Olist**.

Download the dataset from Kaggle and place the source CSV files inside:

```text
data/raw/
```

The local source directory should contain:

```text
data/raw/
├── olist_customers_dataset.csv
├── olist_geolocation_dataset.csv
├── olist_order_items_dataset.csv
├── olist_order_payments_dataset.csv
├── olist_order_reviews_dataset.csv
├── olist_orders_dataset.csv
├── olist_products_dataset.csv
├── olist_sellers_dataset.csv
└── product_category_name_translation.csv
```

The raw CSV files are not stored in this repository.

---

### 5. Configure DuckDB for dbt

The analytical database is created locally using **DuckDB**.

Configure a local dbt profile for the project and point it to:

```text
database/olist.duckdb
```

The dbt project transforms the source data into:

```text
Raw Source Data
      ↓
Staging Models
      ↓
Dimensions + Facts
      ↓
Analytics Models
```

The primary analytical fact tables used by the agent are:

- `fact_customer_orders` — order grain
- `fact_order_items` — order-item grain

Additional analytical models support retention, cohort, and CLTV analysis.

---

### 6. Build the Analytical Models

Navigate to the dbt project:

```bash
cd dbt
```

Verify the dbt connection:

```bash
dbt debug
```

Build the models:

```bash
dbt run
```

After the models are built successfully, the local analytical database will be available at:

```text
database/olist.duckdb
```

Return to the project root:

```bash
cd ..
```

---

### 7. Grounding and Business Definitions

Before querying the database, the agent uses project-specific grounding rather than relying only on the LLM's general knowledge.

The main grounding files are:

```text
docs/metrics.md
docs/data_catalog.md
agent/instructions.md
```

Their responsibilities are:

- **`metrics.md`** — governed business metric definitions
- **`data_catalog.md`** — table grains, relationships, safe joins, and analytical usage
- **`instructions.md`** — agent behavior, validation rules, and operating constraints

For example, the project defines Average Order Value as:

```text
Delivered Revenue / Delivered Orders
```

This allows the agent to use the project's governed definition instead of assuming a generic AOV calculation.

---

### 8. Run the AI Analytics Agent

Make sure:

1. the Python virtual environment is active,
2. Ollama is running,
3. `qwen3:1.7b` is installed,
4. the DuckDB database has been created, and
5. the grounding files are available.

Run the agent from the project root using the project's agent entry point.

The agent workflow is:

```text
Business Question
      ↓
Grounding Selection
      ↓
Qwen Interpretation
      ↓
Analysis Planning + Guardrails
      ↓
SQL Generation / Deterministic Construction
      ↓
Read-Only Database Tool
      ↓
DuckDB Execution
      ↓
Result Validation
      ↓
Business Explanation
```

---

### 9. Example Analytical Questions

Questions used while validating the agent included:

```text
How many item-bearing customers do we have?
```

```text
What is our average order value?
```

```text
What is our repeat purchase rate?
```

```text
How does CLTV differ between repeat and one-time customers?
```

```text
What is total revenue by seller?
```

```text
What is our average order value by product category?
```

Not every question is automatically executed.

If a question contains a material ambiguity or an unsafe grain combination, the agent can stop and request clarification rather than silently generating potentially misleading SQL.

---

### 10. Local-Only Files

The following files are intentionally kept local and are not included in the GitHub repository:

```text
.venv/
database/olist.duckdb
data/raw/*.csv
dbt/target/
dbt/logs/
__pycache__/
```

These files contain local environments, generated artifacts, source datasets, or runtime outputs and can be recreated from the repository and source data.

---

## ⚠️ Project Scope

This project is a portfolio implementation of a **grounded AI-assisted analytics agent**.

It is intentionally designed with:

- a local LLM
- read-only database access
- governed business definitions
- grain-aware analytical validation
- ambiguity handling
- deterministic guardrails for structurally sensitive analysis
- human review for important or ambiguous analytical decisions
---

## Related Analytics Foundation

### 🛒 End-to-End E-commerce Analytics

The original project covers:

- Source-data profiling
- Grain and relationship validation
- Dimensional modeling
- Reusable dbt transformations
- Snowflake analytics models
- SQL business analysis
- Power BI reporting

[View the original analytics repository](https://github.com/narmadapeddi/End-to-End-Ecommerce-Analytics)

---

## 🕵️ Portfolio Case Study

For the complete project story, architecture, model evaluation, and test results:

[View the portfolio case study](https://narmadapeddi9-narmada-peddi-portfo.editor.wix.com/html/editor/web/renderer/edit/c1efbf8c-029b-4113-977d-6616a08e4617?metaSiteId=35d98def-f6db-4767-acf1-d4b993f2bcc9)

---

