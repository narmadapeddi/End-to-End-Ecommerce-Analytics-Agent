"""Minimal grounded analytics-agent loop for local Qwen and DuckDB."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import time
from numbers import Real
from pathlib import Path
from typing import Any

from agent.database_tool import execute_query
from agent.llm_client import generate_response


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GROUNDING_PATHS = (
    PROJECT_ROOT / "docs" / "metrics.md",
    PROJECT_ROOT / "docs" / "data_catalog.md",
    PROJECT_ROOT / "agent" / "instructions.md",
)
DEFAULT_MAX_ITERATIONS = 5
MAX_OBSERVATION_ROWS = 100
FIRST_DECISION_TIMEOUT_SECONDS = int(
    os.getenv("OLIST_FIRST_DECISION_TIMEOUT_SECONDS", "90")
)

METRIC_SECTIONS_ALWAYS = {"Shared governed assumptions"}
CATALOG_SECTIONS_ALWAYS = {"Grain rules", "Relationship map", "Safe-join checklist for the AI"}
POLICY_SECTIONS = {
    "Authority and precedence",
    "Grounding and ambiguity rules",
    "Grain, table, and join rules",
    "SQL and execution safety",
    "Result inspection and validation",
}

TOPIC_RULES = (
    {
        "name": "customer",
        "keywords": ("customer", "customers"),
        "metrics": {"Customer identity and customer count"},
        "catalog": {"fact_customer_orders", "dim_customers"},
    },
    {
        "name": "repeat",
        "keywords": ("repeat", "one-time", "one time"),
        "metrics": {"Repeat Purchase Rate"},
        "catalog": {"fact_customer_orders", "customer_retention_analysis"},
    },
    {
        "name": "retention",
        "keywords": ("retention", "retained"),
        "metrics": {"Customer Retention"},
        "catalog": {"fact_customer_orders", "customer_retention_analysis"},
    },
    {
        "name": "cltv",
        "keywords": ("cltv", "lifetime value"),
        "metrics": {"Customer Lifetime Value (CLTV)"},
        "catalog": {"fact_customer_orders", "product_cltv_analysis"},
    },
    {
        "name": "orders/revenue/aov",
        "keywords": ("aov", "average order value", "revenue", "order", "orders"),
        "metrics": {"Average Order Value (AOV)"},
        "catalog": {"fact_customer_orders", "dim_date"},
    },
    {
        "name": "product",
        "keywords": ("product", "products", "category", "categories", "unit", "units", "asp", "average selling price"),
        "metrics": {"Product Analytics", "Product Revenue", "Units Sold", "Average Selling Price (ASP)"},
        "catalog": {"fact_order_items", "dim_products"},
    },
    {
        "name": "seller",
        "keywords": ("seller", "sellers"),
        "metrics": {"Seller Analytics", "Seller Revenue", "Seller Contribution"},
        "catalog": {"fact_order_items", "dim_sellers"},
    },
    {
        "name": "fulfillment",
        "keywords": ("fulfillment", "delivery", "warehouse", "delivered rate", "carrier"),
        "metrics": {"Fulfillment and Logistics", "Warehouse Processing Time", "Delivery Time", "Delivered Rate"},
        "catalog": {"fact_customer_orders", "dim_date"},
    },
    {
        "name": "cohort",
        "keywords": ("cohort", "cohorts"),
        "metrics": {"Cohort Analysis"},
        "catalog": {"fact_customer_orders", "cohort_analysis"},
    },
)


class AgentProtocolError(ValueError):
    """Raised when the LLM does not follow the action protocol."""


class AgentLoopError(RuntimeError):
    """Raised when the agent cannot finish within its iteration limit."""


class FirstDecisionTimeout(BaseException):
    """Raised when the first local-model decision exceeds its time budget."""


_AMBIGUITY_PATTERNS = (
    r"does not explicitly specify",
    r"does not explicitly name",
    r"not explicitly governed",
    r"implementation ambiguity",
    r"unresolved implementation assumption",
    r"remains an implementation ambiguity",
    r"confirmation is needed",
    r"must be confirmed",
    r"scope remains ambiguous",
)


def _read_grounding_files() -> dict[Path, str]:
    documents: dict[Path, str] = {}
    for path in GROUNDING_PATHS:
        try:
            documents[path] = path.read_text(encoding="utf-8")
        except OSError as error:
            raise AgentLoopError(f"Could not load grounding file {path}: {error}") from error
    return documents


def _parse_markdown_sections(markdown: str) -> dict[str, str]:
    """Split Markdown into deterministic heading sections."""

    matches = list(re.finditer(r"(?m)^(#{1,3})\s+(.+?)\s*$", markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(2).strip().strip("`")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[heading] = markdown[match.start() : end].strip()
    return sections


def _select_named_sections(
    path: Path,
    parsed_sections: dict[str, str],
    requested_headings: set[str],
) -> tuple[list[str], list[str]]:
    content: list[str] = []
    labels: list[str] = []
    for heading, section in parsed_sections.items():
        if heading in requested_headings:
            content.append(section)
            labels.append(f"{path.relative_to(PROJECT_ROOT)} :: {heading}")
    return content, labels


def _select_grounding(question: str) -> tuple[str, list[str], int]:
    documents = _read_grounding_files()
    parsed = {path: _parse_markdown_sections(text) for path, text in documents.items()}
    normalized_question = question.casefold()

    metric_headings = set(METRIC_SECTIONS_ALWAYS)
    catalog_headings = set(CATALOG_SECTIONS_ALWAYS)
    matched_topics: list[str] = []

    for rule in TOPIC_RULES:
        if any(keyword in normalized_question for keyword in rule["keywords"]):
            matched_topics.append(str(rule["name"]))
            metric_headings.update(rule["metrics"])
            catalog_headings.update(rule["catalog"])

    if not matched_topics:
        matched_topics.append("fallback")
        catalog_headings.update({"fact_customer_orders", "fact_order_items", "Question-to-table routing"})
        metric_headings.add("Known definition-to-implementation gaps")

    metrics_path, catalog_path, instructions_path = GROUNDING_PATHS
    selected_parts: list[str] = []
    selected_labels: list[str] = ["topics :: " + ", ".join(matched_topics)]

    for path, headings in (
        (metrics_path, metric_headings),
        (catalog_path, catalog_headings),
        (instructions_path, POLICY_SECTIONS),
    ):
        parts, labels = _select_named_sections(path, parsed[path], headings)
        if parts:
            selected_parts.append(
                f"===== SELECTED FROM {path.relative_to(PROJECT_ROOT)} =====\n"
                + "\n\n".join(parts)
            )
            selected_labels.extend(labels)

    full_grounding_size = sum(len(text) for text in documents.values())
    return "\n\n".join(selected_parts), selected_labels, full_grounding_size


def _detect_material_ambiguity(
    grounding: str, question: str
) -> dict[str, str] | None:
    """Detect explicit ambiguity language in selected governed metric text."""

    metrics_context = grounding.split(
        "===== SELECTED FROM docs/data_catalog.md =====", maxsplit=1
    )[0]
    lowered_context = metrics_context.casefold()
    if not any(re.search(pattern, lowered_context) for pattern in _AMBIGUITY_PATTERNS):
        return None

    ambiguity_type = "status_scope" if "status" in lowered_context else "general"
    normalized_question = question.casefold()
    if ambiguity_type == "status_scope" and any(
        scope in normalized_question
        for scope in ("delivered", "all item-bearing", "all item bearing", "all statuses")
    ):
        return None
    evidence_sentences = re.findall(r"[^\n.!?]+[.!?]", metrics_context)
    evidence = next(
        (
            sentence.strip()
            for sentence in evidence_sentences
            if any(re.search(pattern, sentence.casefold()) for pattern in _AMBIGUITY_PATTERNS)
        ),
        "The governed metric documentation contains an unresolved ambiguity.",
    )
    return {"type": ambiguity_type, "evidence": evidence}


def _clarification_for_ambiguity(ambiguity: dict[str, str]) -> str:
    if ambiguity["type"] == "cross_grain":
        return (
            f"{ambiguity['metric']} is governed at {ambiguity['metric_grain']}, but "
            f"the requested {ambiguity['dimension']} breakdown exists at "
            f"{ambiguity['dimension_grain']}. One order may contain multiple product "
            "categories, so joining order value to item/category rows can repeat the "
            "same order-level measure. No governed attribution rule is documented. "
            "Please choose how to attribute orders: assign each order to one category "
            "using a defined rule, calculate category-associated order value using "
            "distinct orders, or use an item-grain metric such as product revenue or "
            "ASP. I will not query DuckDB until you choose an interpretation."
        )
    if ambiguity["type"] == "status_scope":
        return (
            "Before I calculate this governed metric, please clarify the order-status "
            "scope: should I use all item-bearing orders, or delivered orders only? "
            "The documentation identifies the current all-status behavior as an "
            "implementation assumption rather than a governed status rule. I will not "
            "query DuckDB until you choose the scope."
        )
    return (
        "I found a documented ambiguity that could materially change this result: "
        f"{ambiguity['evidence']} Please clarify the intended interpretation before "
        "I query DuckDB."
    )


def _detect_cross_grain_ambiguity(
    grounding: str, plan: dict[str, Any]
) -> dict[str, str] | None:
    """Block incompatible metric/dimension grains without governed attribution."""

    metric_grain = plan.get("metric_grain")
    dimensions = plan.get("requested_dimensions", [])
    incompatible = next(
        (
            dimension
            for dimension in dimensions
            if metric_grain == "order grain" and dimension["grain"] == "item grain"
        ),
        None,
    )
    if incompatible is None or plan.get("attribution_rule"):
        return None

    normalized_grounding = grounding.casefold()
    authoritative_support = all(
        phrase in normalized_grounding
        for phrase in (
            "aov",
            "order grain",
            "item grain",
            "one-to-many",
            "never sum repeated",
        )
    )
    if not authoritative_support:
        return None

    return {
        "type": "cross_grain",
        "metric": str(plan["governed_metric"]),
        "metric_grain": str(metric_grain),
        "dimension": str(incompatible["name"]),
        "dimension_grain": str(incompatible["grain"]),
        "evidence": (
            "The governed metric and requested breakdown have incompatible grains, "
            "and the documented one-to-many join can repeat the order-level measure."
        ),
    }


def _build_analysis_plan(question: str, grounding: str) -> dict[str, Any]:
    """Derive a compact, deterministic plan from the question and grounding."""

    normalized = question.casefold()
    is_comparison = any(
        term in normalized for term in ("compare", "differ", "difference", " vs ", " versus ")
    )
    plan: dict[str, Any] = {
        "analysis_type": "comparison" if is_comparison else "metric analysis",
        "source": "select according to data_catalog.md",
        "customer_identity": "not applicable",
        "source_grain": "determine from selected grounding",
        "intermediate_grain": "determine from selected grounding",
        "intermediate_calculations": [],
        "final_output_grain": "determine from the requested answer",
        "comparison_dimensions": [],
        "required_measures": [],
        "requires_two_stage_aggregation": False,
        "entity_identifier": None,
        "intermediate_measures": [],
        "classification": None,
        "final_grouping_dimension": None,
        "final_aggregate_measures": [],
        "filters": [],
        "metric_grain": None,
        "requested_dimensions": [],
        "attribution_rule": None,
        "cross_grain_relationship": None,
        "governed_metric": "determine from selected metric definition",
        "comparison_groups": [],
        "status_scope": "not supplied",
        "prohibited": [],
    }

    if "delivered" in normalized:
        plan["status_scope"] = "delivered orders only"
    elif any(term in normalized for term in ("all item-bearing", "all item bearing", "all statuses")):
        plan["status_scope"] = "all item-bearing orders"

    if ("cltv" in normalized or "lifetime value" in normalized) and (
        "Customer Lifetime Value" in grounding
    ):
        plan.update(
            {
                "governed_metric": "historical CLTV = SUM(order_value) per customer",
                "source": "fact_customer_orders",
                "customer_identity": "customer_unique_id",
                "entity_identifier": "customer_unique_id",
                "source_grain": "one row per item-bearing order",
                "intermediate_grain": "one row per customer_unique_id",
                "intermediate_calculations": [
                    "order_count = COUNT(DISTINCT order_id)",
                    "historical_cltv = SUM(order_value)",
                ],
                "intermediate_measures": [
                    {
                        "name": "order_count",
                        "operation": "count_distinct",
                        "column": "order_id",
                    },
                    {
                        "name": "historical_cltv",
                        "operation": "sum",
                        "column": "order_value",
                    },
                ],
                "prohibited": ["product grain", "category grain", "item grain", "fact_order_items"],
            }
        )
        if is_comparison and "repeat" in normalized and any(
            term in normalized for term in ("one-time", "one time")
        ):
            plan["analysis_type"] = "customer-segment comparison"
            plan["comparison_groups"] = [
                "one-time customer = exactly 1 order",
                "repeat customer = more than 1 order",
            ]
            plan["intermediate_calculations"].append(
                "customer_type = one-time when order_count = 1; repeat when order_count > 1"
            )
            plan["final_output_grain"] = "one row per customer_type"
            plan["comparison_dimensions"] = ["customer_type"]
            plan["required_measures"] = [
                "customer_count",
                "total_cltv",
                "average_cltv",
            ]
            plan["requires_two_stage_aggregation"] = True
            plan["classification"] = {
                "name": "customer_type",
                "measure": "order_count",
                "rules": [
                    {"operator": "=", "value": 1, "label": "one-time customer"},
                    {"operator": ">", "value": 1, "label": "repeat customer"},
                ],
            }
            plan["final_grouping_dimension"] = "customer_type"
            plan["final_aggregate_measures"] = [
                {"name": "customer_count", "operation": "count_rows"},
                {
                    "name": "total_cltv",
                    "operation": "sum",
                    "column": "historical_cltv",
                },
                {
                    "name": "average_cltv",
                    "operation": "avg",
                    "column": "historical_cltv",
                },
            ]

    if plan["status_scope"] == "delivered orders only":
        plan["filters"] = [
            {"column": "order_status", "operator": "=", "value": "delivered"}
        ]

    if any(term in normalized for term in ("aov", "average order value")) and (
        "Average Order Value (AOV)" in grounding
    ):
        plan["governed_metric"] = "Average Order Value (AOV)"
        plan["metric_grain"] = "order grain"
        plan["source"] = "fact_customer_orders"
        plan["source_grain"] = "one row per item-bearing order"

    dimension_rules = (
        (
            ("product category", "category", "categories", "product"),
            "product category",
            "item grain",
            ("product_category_name_english", "product_category_name"),
        ),
        (("seller", "sellers"), "seller", "item grain", ("seller_id",)),
        (("month", "monthly"), "month", "order grain", ("month", "date_trunc", "strftime")),
    )
    for keywords, dimension, grain, sql_candidates in dimension_rules:
        if any(keyword in normalized for keyword in keywords):
            plan["requested_dimensions"].append(
                {
                    "name": dimension,
                    "grain": grain,
                    "sql_candidates": list(sql_candidates),
                }
            )

    if plan["requested_dimensions"] and not plan["requires_two_stage_aggregation"]:
        names = ", ".join(
            dimension["name"] for dimension in plan["requested_dimensions"]
        )
        plan["final_output_grain"] = f"one row per {names}"

    if "revenue" in normalized and any(
        dimension["name"] == "seller" for dimension in plan["requested_dimensions"]
    ) and "Seller Revenue" in grounding:
        plan["governed_metric"] = "Seller Revenue = SUM(price)"
        plan["metric_grain"] = "item grain"
        plan["source"] = "fact_order_items"
        plan["source_grain"] = "one row per item position within an order"
        plan["required_measures"] = ["total_revenue"]

    if plan["metric_grain"] == "order grain" and any(
        dimension["grain"] == "item grain" for dimension in plan["requested_dimensions"]
    ):
        plan["cross_grain_relationship"] = "one order to many order items"

    # The selected grounding remains authoritative; include this marker so the
    # model does not treat the deterministic plan as a new metric definition.
    plan["grounding_constraint"] = (
        "Use the selected grounding as authority; this plan only narrows grain and routing."
    )
    return plan


def _format_analysis_plan(plan: dict[str, Any]) -> str:
    groups = plan["comparison_groups"] or ["none"]
    calculations = plan["intermediate_calculations"] or ["none"]
    dimensions = plan["comparison_dimensions"] or ["none"]
    measures = plan["required_measures"] or ["none"]
    prohibited = plan["prohibited"] or ["none"]
    return "\n".join(
        [
            f"Analysis type: {plan['analysis_type']}",
            f"Governed metric: {plan['governed_metric']}",
            f"Metric grain: {plan['metric_grain'] or 'not yet identified'}",
            f"Source: {plan['source']}",
            f"Source/input grain: {plan['source_grain']}",
            f"Customer identity: {plan['customer_identity']}",
            f"Intermediate analytical grain: {plan['intermediate_grain']}",
            "Intermediate calculations:",
            *[f"- {calculation}" for calculation in calculations],
            f"Required final output grain: {plan['final_output_grain']}",
            "Required comparison dimensions:",
            *[f"- {dimension}" for dimension in dimensions],
            "Requested breakdown dimensions:",
            *(
                [
                    f"- {dimension['name']} ({dimension['grain']})"
                    for dimension in plan["requested_dimensions"]
                ]
                or ["- none"]
            ),
            "Required final measures:",
            *[f"- {measure}" for measure in measures],
            "Required query shape: "
            + (
                "two-stage aggregation (customer intermediate, then segment final)"
                if plan["requires_two_stage_aggregation"]
                else "derive from the requested grains"
            ),
            "Groups:",
            *[f"- {group}" for group in groups],
            f"Status scope: {plan['status_scope']}",
            "Do not use:",
            *[f"- {item}" for item in prohibited],
            f"Constraint: {plan['grounding_constraint']}",
        ]
    )


def _sql_identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise AgentLoopError(f"Unsafe or invalid planner SQL identifier: {value!r}")
    return value


def _sql_literal(value: Any) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, Real) and not isinstance(value, bool):
        return str(value)
    raise AgentLoopError(f"Unsupported planner SQL literal: {value!r}")


def _aggregate_expression(specification: dict[str, Any]) -> str:
    operation = specification["operation"]
    name = _sql_identifier(specification["name"])
    if operation == "count_rows":
        expression = "COUNT(*)"
    else:
        column = _sql_identifier(specification["column"])
        functions = {
            "count_distinct": f"COUNT(DISTINCT {column})",
            "sum": f"SUM({column})",
            "avg": f"AVG({column})",
        }
        if operation not in functions:
            raise AgentLoopError(f"Unsupported planner aggregation: {operation!r}")
        expression = functions[operation]
    return f"{expression} AS {name}"


def _build_multistage_comparison_sql(plan: dict[str, Any]) -> str | None:
    """Build SQL from validated planner metadata for multi-stage comparisons."""

    if not plan.get("requires_two_stage_aggregation"):
        return None

    source = _sql_identifier(plan["source"])
    entity = _sql_identifier(plan["entity_identifier"])
    intermediate_measures = plan["intermediate_measures"]
    classification = plan["classification"]
    final_dimension = _sql_identifier(plan["final_grouping_dimension"])
    final_measures = plan["final_aggregate_measures"]
    if not intermediate_measures or not classification or not final_measures:
        raise AgentLoopError("Multi-stage comparison planner metadata is incomplete.")

    filter_clauses: list[str] = []
    for filter_specification in plan["filters"]:
        column = _sql_identifier(filter_specification["column"])
        operator = filter_specification["operator"]
        if operator not in {"=", "!=", ">", ">=", "<", "<="}:
            raise AgentLoopError(f"Unsupported planner filter operator: {operator!r}")
        filter_clauses.append(
            f"{column} {operator} {_sql_literal(filter_specification['value'])}"
        )
    where_clause = "\n    WHERE " + " AND ".join(filter_clauses) if filter_clauses else ""

    classification_name = _sql_identifier(classification["name"])
    classification_measure = _sql_identifier(classification["measure"])
    if classification_name != final_dimension:
        raise AgentLoopError("Classification output must match the final grouping dimension.")
    case_lines: list[str] = []
    for rule in classification["rules"]:
        operator = rule["operator"]
        if operator not in {"=", "!=", ">", ">=", "<", "<="}:
            raise AgentLoopError(f"Unsupported classification operator: {operator!r}")
        case_lines.append(
            f"WHEN {classification_measure} {operator} {_sql_literal(rule['value'])} "
            f"THEN {_sql_literal(rule['label'])}"
        )

    intermediate_sql = ",\n        ".join(
        _aggregate_expression(specification) for specification in intermediate_measures
    )
    final_sql = ",\n    ".join(
        _aggregate_expression(specification) for specification in final_measures
    )
    case_sql = "\n            ".join(case_lines)

    return f"""WITH entity_metrics AS (
    SELECT
        {entity},
        {intermediate_sql}
    FROM {source}{where_clause}
    GROUP BY {entity}
),
classified_entities AS (
    SELECT
        *,
        CASE
            {case_sql}
            ELSE 'unclassified'
        END AS {classification_name}
    FROM entity_metrics
)
SELECT
    {final_dimension},
    {final_sql}
FROM classified_entities
GROUP BY {final_dimension}
ORDER BY {final_dimension}"""


def _remove_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```sql"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_decision(response: str) -> tuple[str, str]:
    normalized_response = response.replace("**", "")
    action_matches = list(
        re.finditer(r"(?i)\bACTION\s*:\s*(QUERY|ANSWER)\b", normalized_response)
    )
    if len(action_matches) != 1:
        raise AgentProtocolError(
            "LLM response must contain exactly one ACTION: QUERY or ACTION: ANSWER line."
        )

    action_match = action_matches[0]
    action = action_match.group(1).upper()
    field_name = "SQL" if action == "QUERY" else "ANSWER"
    field_match = re.search(
        rf"(?ims)^\s*{field_name}\s*:\s*(.+)\Z",
        normalized_response[action_match.end() :],
    )
    if not field_match:
        trailing = normalized_response[action_match.end() :].strip()
        if action == "QUERY":
            fenced_sql = re.search(r"(?is)```sql\s*(.+?)\s*```", trailing)
            if not fenced_sql:
                raise AgentProtocolError("ACTION: QUERY requires a SQL: field or SQL code fence.")
            content = fenced_sql.group(1).strip()
        elif trailing:
            content = trailing
        else:
            raise AgentProtocolError("ACTION: ANSWER requires answer content.")
    else:
        content = _remove_code_fence(field_match.group(1))

    if not content:
        raise AgentProtocolError(f"The {field_name}: field cannot be empty.")
    if action == "ANSWER":
        lines = content.splitlines()
        if (
            len(lines) > 1
            and re.fullmatch(r"[a-z][a-z0-9_]*", lines[0].strip())
            and re.match(r"(?i)^\s*ANSWER\s*:", lines[1])
        ):
            lines = lines[1:]
        lines = [re.sub(r"(?i)^\s*ANSWER\s*:\s*", "", line) for line in lines]
        content = "\n".join(lines).strip()
    return action, content


def _format_observation(result: dict[str, Any]) -> str:
    rows = result["rows"]
    displayed_rows = rows[:MAX_OBSERVATION_ROWS]
    payload = {
        "columns": result["columns"],
        "row_count": len(rows),
        "rows": displayed_rows,
        "truncated": len(rows) > len(displayed_rows),
    }
    return json.dumps(payload, default=str, ensure_ascii=False)


def _format_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "No prior decisions or observations."

    entries: list[str] = []
    for event in history:
        event_type = event["type"]
        if event_type == "query":
            entries.append(f"LLM requested QUERY:\n{event['sql']}")
        elif event_type == "result":
            entries.append(f"DATABASE RESULT:\n{event['observation']}")
        elif event_type == "error":
            entries.append(f"DATABASE/PROTOCOL ERROR:\n{event['error']}")
        elif event_type == "rejected_answer":
            entries.append(
                "ANSWER REJECTED because this run requires a successful database "
                f"query first:\n{event['answer']}"
            )
        elif event_type == "answer_validation_error":
            entries.append(
                "FINAL ANSWER REJECTED:\n"
                f"{event['error']}\nRejected answer:\n{event['answer']}"
            )
    return "\n\n".join(entries)


def _latest_successful_result(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(history):
        if event["type"] == "result":
            return event["result"]
    return None


def _latest_result_instruction(history: list[dict[str, Any]]) -> str:
    latest_result = _latest_successful_result(history)
    if latest_result is None:
        return "No successful DuckDB observation exists yet."
    return f"""LATEST SUCCESSFUL DUCKDB OBSERVATION (AUTHORITATIVE FOR CURRENT NUMBERS)
{_format_observation(latest_result)}

Use this latest successful result for every numeric claim in the current answer.
Treat numbers in grounding, failed attempts, earlier iterations, previous scopes,
and previous conversations as historical context only. Ensure numerator,
denominator, rate, filters, and scope are internally consistent. Do not mention a
number unless the latest successful observation supports it."""


def _numeric_values(result: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for row in result["rows"]:
        for value in row:
            if isinstance(value, Real) and not isinstance(value, bool):
                values.append(float(value))
    return values


def _rate_display_values(question: str, result: dict[str, Any]) -> list[str]:
    """Format raw decimal ratios for presentation without changing observations."""

    rate_terms = ("rate", "ratio", "percentage", "retention", "contribution")
    question_is_rate = any(term in question.casefold() for term in rate_terms)
    formatted: list[str] = []
    for column_index, column in enumerate(result["columns"]):
        column_is_rate = any(term in str(column).casefold() for term in rate_terms)
        if not (column_is_rate or (question_is_rate and len(result["columns"]) == 1)):
            continue
        for row in result["rows"]:
            value = row[column_index]
            if isinstance(value, Real) and not isinstance(value, bool):
                percentage = float(value) * 100
                display = f"{percentage:.4f}".rstrip("0").rstrip(".")
                if "." in display and len(display.partition(".")[2]) < 2:
                    display = f"{percentage:.2f}"
                formatted.append(f"{column}: {display}%")
    return formatted


def _ratio_consistency_error(result: dict[str, Any]) -> str | None:
    if len(result["rows"]) != 1:
        return None
    columns = [str(column).casefold() for column in result["columns"]]
    row = result["rows"][0]
    numeric_indices = [
        index
        for index, value in enumerate(row)
        if isinstance(value, Real) and not isinstance(value, bool)
    ]
    rate_indices = [
        index
        for index in numeric_indices
        if any(word in columns[index] for word in ("rate", "ratio", "percentage"))
    ]
    denominator_indices = [
        index
        for index in numeric_indices
        if any(word in columns[index] for word in ("denominator", "total"))
    ]
    if len(rate_indices) != 1 or len(denominator_indices) != 1:
        return None
    remaining = [
        index
        for index in numeric_indices
        if index not in {rate_indices[0], denominator_indices[0]}
    ]
    numerator_indices = [
        index
        for index in remaining
        if "numerator" in columns[index]
        or not any(word in columns[index] for word in ("rate", "ratio", "total"))
    ]
    if len(numerator_indices) != 1:
        return None

    numerator = float(row[numerator_indices[0]])
    denominator = float(row[denominator_indices[0]])
    rate = float(row[rate_indices[0]])
    if denominator == 0:
        return "Latest result has a zero denominator, so its reported rate cannot be validated."
    expected_rate = numerator / denominator
    if abs(rate - expected_rate) > max(1e-9, abs(expected_rate) * 1e-7):
        return (
            "Latest result is internally inconsistent: the reported rate does not "
            "match numerator / denominator."
        )
    return None


def _answer_numeric_consistency_error(
    answer: str, result: dict[str, Any]
) -> str | None:
    ratio_error = _ratio_consistency_error(result)
    if ratio_error:
        return ratio_error

    authoritative_values = _numeric_values(result)
    if not authoritative_values:
        return None

    rate_columns = (
        "rate",
        "ratio",
        "percentage",
        "retention",
        "contribution",
    )
    has_rate_metric = any(
        any(term in str(column).casefold() for term in rate_columns)
        for column in result["columns"]
    )
    if has_rate_metric and "%" not in answer:
        return (
            "A rate or ratio result must be presented as a percentage with "
            "reasonable precision, while validation continues to use the raw decimal."
        )

    for match in re.finditer(r"(?<![A-Za-z_])[-+]?\d[\d,]*(?:\.\d+)?%?", answer):
        token = match.group(0)
        is_percent = token.endswith("%")
        numeric_text = token.rstrip("%").replace(",", "")
        reported_value = float(numeric_text)
        decimal_places = len(numeric_text.partition(".")[2])
        normalized_value = reported_value / 100.0 if is_percent else reported_value
        rounding_tolerance = 0.5 * (10 ** (-decimal_places))
        if is_percent:
            rounding_tolerance /= 100.0
        supported = any(
            abs(normalized_value - value)
            <= max(1e-9, rounding_tolerance + abs(value) * 1e-9)
            for value in authoritative_values
        )
        if not supported:
            return (
                f"Numeric value {token} is not supported by the latest successful "
                "DuckDB observation."
            )
    return None


def _query_scope_consistency_error(question: str, sql: str) -> str | None:
    """Ensure an explicit user-provided status scope is present in SQL."""

    normalized_question = question.casefold()
    normalized_sql = sql.casefold()
    if "delivered" in normalized_question and not (
        "order_status" in normalized_sql and "delivered" in normalized_sql
    ):
        return (
            "The user explicitly requested delivered orders only, but the SQL does "
            "not apply order_status = 'delivered'. Regenerate SQL with that scope."
        )
    return None


def _query_plan_consistency_error(sql: str, plan: dict[str, Any]) -> str | None:
    """Reject SQL that contradicts deterministic grain and routing constraints."""

    normalized_sql = sql.casefold()
    prohibited_tokens = {
        "product grain": ("product_id",),
        "category grain": ("product_category",),
        "item grain": ("order_item_id",),
        "fact_order_items": ("fact_order_items",),
    }
    violations = [
        label
        for label in plan["prohibited"]
        if any(token in normalized_sql for token in prohibited_tokens.get(label, ()))
    ]
    if violations:
        return (
            "The SQL contradicts the deterministic analysis plan by using: "
            f"{', '.join(violations)}. Regenerate SQL with intermediate grain "
            f"{plan['intermediate_grain']} using {plan['source']} only."
        )

    select_match = re.search(r"(?is)\bselect\b(.*?)\bfrom\b", normalized_sql)
    select_clause = select_match.group(1) if select_match else ""
    group_matches = list(re.finditer(r"(?is)\bgroup\s+by\b(.*?)(?:\bhaving\b|\border\s+by\b|\blimit\b|\Z)", normalized_sql))
    final_group_clause = group_matches[-1].group(1) if group_matches else ""
    uses_aggregation = bool(re.search(r"(?i)\b(sum|avg|count|min|max)\s*\(", select_clause))
    for dimension in plan.get("requested_dimensions", []):
        candidates = [candidate.casefold() for candidate in dimension["sql_candidates"]]
        selected = any(candidate in select_clause for candidate in candidates)
        grouped = any(candidate in final_group_clause for candidate in candidates)
        if not selected or (uses_aggregation and not grouped):
            return (
                f"The user requested results by {dimension['name']}, but the SQL "
                f"does not produce {plan['final_output_grain']}. Include the requested "
                "dimension in the final SELECT and GROUP BY before treating the query "
                "as evidence."
            )

    required_dimensions = plan["comparison_dimensions"]
    required_measures = plan["required_measures"]
    if required_dimensions and required_measures:
        missing_dimensions = [
            dimension
            for dimension in required_dimensions
            if dimension.casefold() not in normalized_sql
        ]
        missing_measures = [
            measure for measure in required_measures if measure.casefold() not in normalized_sql
        ]
        final_grouping_present = all(
            re.search(rf"(?is)group\s+by[\s\S]*\b{re.escape(dimension.casefold())}\b", normalized_sql)
            for dimension in required_dimensions
        )
        if missing_dimensions or missing_measures or not final_grouping_present:
            missing = missing_dimensions + missing_measures
            details = ", ".join(missing) if missing else "final comparison GROUP BY"
            return (
                "The SQL stops at the intermediate analytical grain and does not "
                f"produce {plan['final_output_grain']}. Missing final comparison "
                f"requirements: {details}. Regenerate SQL with every required "
                "comparison dimension and measure from the plan."
            )
        if plan["requires_two_stage_aggregation"] and not (
            re.match(r"(?is)^\s*with\b", normalized_sql)
            or re.search(r"(?is)\bfrom\s*\(", normalized_sql)
        ):
            return (
                "The SQL collapses the intermediate customer calculation and final "
                "segment comparison into one aggregation. Use a two-stage read-only "
                "query: first produce one row per customer, then group those rows by "
                "the required comparison dimension and calculate every final measure."
            )
    return None


def _result_plan_consistency_error(
    result: dict[str, Any], plan: dict[str, Any]
) -> str | None:
    columns = [str(column).casefold() for column in result["columns"]]
    for dimension in plan.get("requested_dimensions", []):
        candidates = [candidate.casefold() for candidate in dimension["sql_candidates"]]
        if not any(any(candidate in column for candidate in candidates) for column in columns):
            return (
                f"The successful query result does not contain the requested final "
                f"dimension {dimension['name']}; it cannot support the answer."
            )
    return None


def _successful_sql(history: list[dict[str, Any]]) -> list[str]:
    successful: list[str] = []
    pending_sql: str | None = None
    for event in history:
        if event["type"] == "query":
            pending_sql = event["sql"]
        elif event["type"] == "result" and pending_sql is not None:
            successful.append(pending_sql)
            pending_sql = None
        elif event["type"] == "error":
            pending_sql = None
    return successful


def _deterministic_evidence_fallback(
    plan: dict[str, Any], history: list[dict[str, Any]]
) -> tuple[str, str] | None:
    """Finalize from validated evidence when the LLM cannot follow the protocol."""

    result = _latest_successful_result(history)
    successful_sql = _successful_sql(history)
    if result is None or not successful_sql:
        return None

    latest_sql = successful_sql[-1]
    columns = [str(column) for column in result["columns"]]
    preview_rows = result["rows"][:3]
    status_scope = str(plan.get("status_scope", "not supplied"))
    if status_scope == "not supplied":
        status_scope = (
            "not supplied; the executed SQL applied no WHERE filter"
            if not re.search(r"(?i)\bwhere\b", latest_sql)
            else "not supplied; use the executed SQL shown in the trace for filters"
        )

    answer = (
        "Deterministic evidence fallback (LLM finalization was unavailable). "
        f"Metric: {plan['governed_metric']}. "
        f"Result grain: {plan['final_output_grain']}. "
        f"DuckDB returned {len(result['rows']):,} rows with columns "
        f"{', '.join(columns)}. Status/filter scope: {status_scope}. "
        "Preview of the first validated rows: "
        f"{json.dumps(preview_rows, default=str, ensure_ascii=False)}"
    )
    return answer, latest_sql


def _answer_sql_evidence_error(answer: str, history: list[dict[str, Any]]) -> str | None:
    proposed_sql = re.findall(r"(?is)```sql\s*(.*?)\s*```", answer)
    if not proposed_sql:
        return None

    normalize = lambda sql: re.sub(r"\s+", " ", sql.strip().rstrip(";")).casefold()
    executed = {normalize(sql) for sql in _successful_sql(history)}
    if any(normalize(sql) not in executed for sql in proposed_sql):
        return (
            "The final answer contains SQL that was not successfully executed and "
            "validated by DuckDB. Proposed SQL is not analytical evidence."
        )
    return None


def _build_prompt(
    question: str,
    grounding: str,
    analysis_plan: str,
    history: list[dict[str, Any]],
    require_query: bool,
    successful_queries: int,
) -> str:
    if history and history[-1].get("type") == "error" and any(
        phrase in history[-1]["error"]
        for phrase in ("exactly one ACTION", "requires answer content", "requires a SQL")
    ):
        return f"""/no_think
Your previous response violated the action protocol. The grounding was already
provided. Follow the deterministic analysis plan below and return exactly one
action with no explanation, headings, or surrounding prose.

For a query, return exactly:
ACTION: QUERY
SQL:
<one read-only DuckDB SELECT or WITH query>

Do not answer yet: this run requires a successful DuckDB query. Do not use any
grain or table prohibited by the plan. The LLM must generate the SQL itself.

ORIGINAL QUESTION
{question}

DETERMINISTIC ANALYSIS PLAN
{analysis_plan}
"""

    validation_errors = [
        event for event in history if event.get("type") == "answer_validation_error"
    ]
    if validation_errors:
        latest_result = _latest_successful_result(history)
        rate_display_values = _rate_display_values(question, latest_result)
        presentation_values = (
            "\n".join(rate_display_values)
            if rate_display_values
            else "No percentage conversion is required."
        )
        return f"""/no_think
Your previous final answer was rejected because it conflicted with the current
successful DuckDB observation. Regenerate the answer using only that observation
for numeric claims. Do not use numeric values from grounding, earlier iterations,
failed SQL, historical reference values, or previous scope assumptions.

Return exactly:
ACTION: ANSWER
ANSWER:
<actual natural-language answer>

The answer must:
- use the latest successful DuckDB result for every current numeric claim;
- present rate, percentage, retention, repeat-purchase, delivered-rate,
  contribution-rate, and similar ratio values as percentages by multiplying the
  raw decimal by 100 and using 2-4 decimal places;
- otherwise reproduce numeric values as represented in the observation;
- keep numerator, denominator, rate, filters, and scope internally consistent;
- omit any number not supported by the latest successful observation;
- preserve the user's requested scope;
- contain no template placeholders or repeated ANSWER labels.

ORIGINAL QUESTION
{question}

DETERMINISTIC ANALYSIS PLAN
{analysis_plan}

LATEST SUCCESSFUL DUCKDB OBSERVATION (AUTHORITATIVE)
{json.dumps(latest_result, default=str)}

DETERMINISTIC PRESENTATION VALUE
{presentation_values}
Use this display value exactly in the natural-language answer. It is derived from
the raw observation above; the raw observation remains authoritative for validation.

LATEST VALIDATION ERROR
{validation_errors[-1]['error']}
"""

    query_requirement = (
        "This run requires at least one successful database query before you may "
        "return ACTION: ANSWER."
        if require_query and successful_queries == 0
        else "You may answer when the available evidence is sufficient."
    )

    return f"""/no_think
You are the Olist AI analytics agent.

Follow the grounding documents below. Their authority and operating rules are
binding. Do not invent metric definitions or database structure.

Return exactly one action and no text outside that action.

To request data:
ACTION: QUERY
SQL:
<one read-only DuckDB SELECT or WITH query>

To provide the final response, output an ACTION: ANSWER line followed by an
ANSWER: label and then the actual natural-language answer. Never repeat template
or placeholder text. Include the definition, tables/grain, filters/status scope,
material caveats, and validation when relevant.

Rules for this step:
- {query_requirement}
- Use only columns and relations documented in the grounding.
- Keep SQL concise and aggregate in the database.
- Do not request file or database modification.
- Use prior database observations as evidence.
- If a database error appears in history, correct the SQL if possible.
- For ratio metrics, return numerator, denominator, and rate as separate columns
  in the same SQL result whenever possible.
- Present rate, percentage, retention, repeat-purchase, delivered-rate,
  contribution-rate, and similar ratio results as percentages with 2-4 decimal
  places. Keep the raw database decimal as the validation value.

{_latest_result_instruction(history)}

DETERMINISTIC ANALYSIS PLAN
{analysis_plan}
Follow this plan when choosing grain, groups, and source. Do not substitute a
prohibited grain or table. The selected grounding remains authoritative.

GROUNDING
{grounding}

ORIGINAL QUESTION
{question}

HISTORY
{_format_history(history)}
"""


def _trace(message: str, enabled: bool) -> None:
    if enabled:
        print(message, flush=True)


def _generate_first_decision(prompt: str) -> str:
    """Call the local model with a hard ceiling for the first decision."""

    def timeout_handler(signum: int, frame: Any) -> None:
        del signum, frame
        raise FirstDecisionTimeout(
            f"First LLM decision exceeded {FIRST_DECISION_TIMEOUT_SECONDS} seconds."
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, FIRST_DECISION_TIMEOUT_SECONDS)
    try:
        return generate_response(prompt)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_agent(
    question: str,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_query: bool = False,
    show_trace: bool = False,
) -> dict[str, Any]:
    """Answer one natural-language question through the LLM/query loop."""

    if not isinstance(question, str):
        raise TypeError("question must be a string.")
    if not question.strip():
        raise ValueError("question cannot be empty.")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1.")

    started_at = time.perf_counter()
    grounding, selected_sections, full_grounding_size = _select_grounding(question)
    analysis_plan_data = _build_analysis_plan(question, grounding)
    analysis_plan = _format_analysis_plan(analysis_plan_data)
    history: list[dict[str, Any]] = []
    successful_queries = 0
    answer_regenerations = 0

    _trace(f"QUESTION: {question}", show_trace)
    _trace("SELECTED GROUNDING SECTIONS:", show_trace)
    for section in selected_sections:
        _trace(f"- {section}", show_trace)
    _trace(f"ANALYSIS PLAN:\n{analysis_plan}", show_trace)

    initial_prompt = _build_prompt(
        question, grounding, analysis_plan, history, require_query, 0
    )
    selected_prompt_size = len(initial_prompt)
    full_prompt_estimate = selected_prompt_size - len(grounding) + full_grounding_size
    _trace(
        "APPROXIMATE PROMPT SIZE: "
        f"before={full_prompt_estimate:,} chars (~{full_prompt_estimate // 4:,} tokens), "
        f"after={selected_prompt_size:,} chars (~{selected_prompt_size // 4:,} tokens)",
        show_trace,
    )

    ambiguity = _detect_material_ambiguity(grounding, question)
    if ambiguity is None:
        ambiguity = _detect_cross_grain_ambiguity(grounding, analysis_plan_data)
    if ambiguity is not None:
        answer = _clarification_for_ambiguity(ambiguity)
        runtime_seconds = time.perf_counter() - started_at
        _trace(f"MATERIAL AMBIGUITY DETECTED: {ambiguity['evidence']}", show_trace)
        _trace("SQL GENERATION SKIPPED", show_trace)
        _trace(f"FINAL ANSWER: {answer}", show_trace)
        _trace(f"TOTAL RUNTIME: {runtime_seconds:.2f} seconds", show_trace)
        return {
            "question": question,
            "answer": answer,
            "iterations": 0,
            "successful_queries": 0,
            "history": [],
            "selected_grounding_sections": selected_sections,
            "prompt_size_before_chars": full_prompt_estimate,
            "prompt_size_after_chars": selected_prompt_size,
            "runtime_seconds": runtime_seconds,
            "ambiguity": ambiguity,
        }

    builder_sql = _build_multistage_comparison_sql(analysis_plan_data)
    builder_invoked = builder_sql is not None
    if builder_sql is not None:
        history.append({"type": "query", "sql": builder_sql, "origin": "builder"})
        _trace("DETERMINISTIC SQL BUILDER INVOKED", show_trace)
        _trace(f"BUILDER SQL:\n{builder_sql}", show_trace)
        try:
            result = execute_query(builder_sql)
        except Exception as error:
            error_message = f"{type(error).__name__}: {error}"
            history.append({"type": "error", "error": error_message})
            _trace(f"BUILDER DATABASE ERROR: {error_message}", show_trace)
        else:
            result_error = _result_plan_consistency_error(result, analysis_plan_data)
            if result_error:
                history.append({"type": "error", "error": result_error})
                _trace(f"BUILDER RESULT GRAIN ERROR: {result_error}", show_trace)
            else:
                successful_queries += 1
                observation = _format_observation(result)
                history.append(
                    {"type": "result", "observation": observation, "result": result}
                )
                _trace(f"DUCKDB RESULT: {observation}", show_trace)
                _trace("BUILDER RESULT RETURNED TO LLM", show_trace)

    for iteration in range(1, max_iterations + 1):
        prompt = _build_prompt(
            question,
            grounding,
            analysis_plan,
            history,
            require_query,
            successful_queries,
        )
        try:
            response = (
                _generate_first_decision(prompt)
                if iteration == 1
                else generate_response(prompt)
            )
        except FirstDecisionTimeout as error:
            runtime_seconds = time.perf_counter() - started_at
            _trace(f"FIRST DECISION TIMEOUT: {error}", show_trace)
            _trace(f"TOTAL RUNTIME: {runtime_seconds:.2f} seconds", show_trace)
            raise AgentLoopError(str(error)) from error

        try:
            action, content = _parse_decision(response)
        except AgentProtocolError as error:
            protocol_error = str(error)
            history.append({"type": "error", "error": protocol_error})
            _trace(f"ITERATION {iteration} PROTOCOL ERROR: {error}", show_trace)
            _trace(f"RAW LLM RESPONSE: {response}", show_trace)
            continue

        _trace(f"ITERATION {iteration} LLM ACTION: {action}", show_trace)

        if action == "ANSWER":
            if require_query and successful_queries == 0:
                history.append({"type": "rejected_answer", "answer": content})
                _trace("ANSWER REJECTED: successful query required first", show_trace)
                continue
            latest_result = _latest_successful_result(history)
            if latest_result is not None:
                consistency_error = _answer_sql_evidence_error(content, history)
                if consistency_error is None:
                    consistency_error = _answer_numeric_consistency_error(
                        content, latest_result
                    )
                if consistency_error:
                    answer_regenerations += 1
                    history.append(
                        {
                            "type": "answer_validation_error",
                            "error": consistency_error,
                            "answer": content,
                        }
                    )
                    _trace(
                        f"FINAL ANSWER REJECTED: {consistency_error}", show_trace
                    )
                    continue
            _trace(f"FINAL ANSWER: {content}", show_trace)
            runtime_seconds = time.perf_counter() - started_at
            _trace(f"TOTAL RUNTIME: {runtime_seconds:.2f} seconds", show_trace)
            return {
                "question": question,
                "answer": content,
                "iterations": iteration,
                "successful_queries": successful_queries,
                "history": history,
                "selected_grounding_sections": selected_sections,
                "prompt_size_before_chars": full_prompt_estimate,
                "prompt_size_after_chars": selected_prompt_size,
                "runtime_seconds": runtime_seconds,
                "answer_regenerations": answer_regenerations,
                "analysis_plan": analysis_plan_data,
                "builder_invoked": builder_invoked,
                "builder_sql": builder_sql,
                "finalization": "llm",
                "llm_finalization_succeeded": True,
            }

        sql = content
        history.append({"type": "query", "sql": sql})
        _trace(f"SQL:\n{sql}", show_trace)

        scope_error = _query_scope_consistency_error(question, sql)
        if scope_error:
            history.append({"type": "error", "error": scope_error})
            _trace(f"QUERY SCOPE ERROR: {scope_error}", show_trace)
            continue

        plan_error = _query_plan_consistency_error(sql, analysis_plan_data)
        if plan_error:
            history.append({"type": "error", "error": plan_error})
            _trace(f"QUERY PLAN ERROR: {plan_error}", show_trace)
            continue

        try:
            result = execute_query(sql)
        except Exception as error:  # Returned to the LLM so it can repair SQL.
            error_message = f"{type(error).__name__}: {error}"
            history.append({"type": "error", "error": error_message})
            _trace(f"DATABASE ERROR: {error_message}", show_trace)
            continue

        result_error = _result_plan_consistency_error(result, analysis_plan_data)
        if result_error:
            history.append({"type": "error", "error": result_error})
            _trace(f"RESULT GRAIN ERROR: {result_error}", show_trace)
            continue

        successful_queries += 1
        observation = _format_observation(result)
        history.append(
            {"type": "result", "observation": observation, "result": result}
        )
        _trace(f"DUCKDB RESULT: {observation}", show_trace)
        _trace("RESULT RETURNED TO LLM", show_trace)

    fallback = _deterministic_evidence_fallback(analysis_plan_data, history)
    if fallback is not None:
        answer, evidence_sql = fallback
        runtime_seconds = time.perf_counter() - started_at
        _trace("LLM FINALIZATION FAILED; DETERMINISTIC FALLBACK INVOKED", show_trace)
        _trace(f"FINAL ANSWER: {answer}", show_trace)
        _trace(f"TOTAL RUNTIME: {runtime_seconds:.2f} seconds", show_trace)
        return {
            "question": question,
            "answer": answer,
            "iterations": max_iterations,
            "successful_queries": successful_queries,
            "history": history,
            "selected_grounding_sections": selected_sections,
            "prompt_size_before_chars": full_prompt_estimate,
            "prompt_size_after_chars": selected_prompt_size,
            "runtime_seconds": runtime_seconds,
            "answer_regenerations": answer_regenerations,
            "analysis_plan": analysis_plan_data,
            "builder_invoked": builder_invoked,
            "builder_sql": builder_sql,
            "finalization": "deterministic_fallback",
            "llm_finalization_succeeded": False,
            "evidence_sql": evidence_sql,
        }

    raise AgentLoopError(
        f"Agent did not produce a final answer within {max_iterations} iterations. "
        f"History: {json.dumps(history, default=str)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the minimal Olist analytics agent.")
    parser.add_argument("question", help="Natural-language business question")
    parser.add_argument("--require-query", action="store_true")
    parser.add_argument("--show-trace", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    arguments = parser.parse_args()

    result = run_agent(
        arguments.question,
        max_iterations=arguments.max_iterations,
        require_query=arguments.require_query,
        show_trace=arguments.show_trace,
    )
    if not arguments.show_trace:
        print(result["answer"])


if __name__ == "__main__":
    main()
