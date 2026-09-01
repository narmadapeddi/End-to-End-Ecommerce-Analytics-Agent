## AI Analytics Agent

This folder contains the core implementation of the AI-assisted analytics agent.

The agent uses a local Qwen LLM through Ollama to interpret business questions, applies project-specific grounding and analytical guardrails, queries the DuckDB analytics layer, validates the returned results, and produces a business-friendly response.

## Agent Flow

Business Question  
→ Grounding Selection  
→ LLM Interpretation  
→ Analysis Planning & Guardrails  
→ SQL Generation / Construction  
→ Read-Only DuckDB Execution  
→ Result Validation  
→ Business Explanation

## Files

### `analytics_agent.py`
Main orchestration layer for the agent.

Responsible for:
- receiving natural-language business questions
- selecting relevant grounding
- determining analytical requirements and grain
- detecting ambiguity and cross-grain conflicts
- coordinating SQL generation and execution
- validating query outputs
- returning evidence-backed answers

### `llm_client.py`
Connects the Python agent to the local Qwen model through Ollama.

It handles communication between the orchestration layer and the LLM.

### `database_tool.py`
Provides controlled access to the DuckDB analytical database.

It:
- accepts SQL from the agent
- enforces read-only execution
- blocks destructive operations
- executes validated queries
- returns database results to the agent

### `instructions.md`
Defines the operating rules followed by the agent.

These instructions emphasize:
- governed business definitions
- grain-first analysis
- ambiguity handling
- safe joins
- read-only SQL
- result validation
- evidence-based explanations

## Design Principle

The LLM is not treated as the source of truth.

Business definitions and data structure come from the project's grounding documentation, while numerical results come from DuckDB. Deterministic guardrails are used where relying only on LLM-generated SQL could produce analytically incorrect results.
