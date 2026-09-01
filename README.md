## 🤖 End-to-End E-commerce Analytics Agent

A local analytics agent built on my e-commerce dimensional model to answer business questions using governed metrics, validated SQL, and practical guardrails.

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
├── ADD_PROJECT_FOLDERS_HERE
└── ADD_PROJECT_FILES_HERE
```

This section will be updated after the final repository files are organized.

---

## 🖥️ Running the Project Locally

Detailed setup instructions will be added after the repository structure and entry point are finalized.

The final instructions should cover:

1. Installing the required local tools
2. Downloading the selected Ollama model
3. Preparing the DuckDB analytical database
4. Configuring the grounding files
5. Starting the agent
6. Running the test scenarios

---

## Related Project

### 🛒 End-to-End E-commerce Analytics

The original project covers:

- Source-data profiling
- Grain and relationship validation
- Dimensional modeling
- Reusable dbt transformations
- Snowflake analytics models
- SQL business analysis
- Power BI reporting

[View the original analytics repository](ADD_ORIGINAL_REPOSITORY_LINK)

---

## 🕵️ Portfolio Case Study

For the complete project story, architecture, model evaluation, and test results:

[View the portfolio case study](ADD_PORTFOLIO_LINK)

---

## 👤 Author

**Narmada Peddi**

- [LinkedIn](ADD_LINKEDIN_LINK)
- [Portfolio](ADD_PORTFOLIO_LINK)
- [GitHub](ADD_GITHUB_PROFILE_LINK)
