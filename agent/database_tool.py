"""Read-only DuckDB query connector for the Olist analytics agent."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "database" / "olist.duckdb"


class UnsafeQueryError(ValueError):
    """Raised when SQL does not satisfy the connector's read-only policy."""


class DatabaseQueryError(RuntimeError):
    """Raised when DuckDB cannot execute an otherwise permitted query."""


_ALLOWED_START_KEYWORDS = {"SELECT", "WITH"}

# These tokens are prohibited anywhere outside quoted strings, quoted
# identifiers, and comments. The read-only DuckDB connection is an independent
# second layer of protection against database mutation.
_FORBIDDEN_KEYWORDS = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "BEGIN",
    "CALL",
    "CHECKPOINT",
    "COMMENT",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "EXPORT",
    "IMPORT",
    "INSERT",
    "INSTALL",
    "LOAD",
    "MERGE",
    "PRAGMA",
    "REINDEX",
    "RESET",
    "ROLLBACK",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "USE",
    "VACUUM",
}


def _mask_literals_identifiers_and_comments(sql: str) -> str:
    """Replace quoted/comment content with spaces while preserving SQL shape."""

    output: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]
        following = sql[index + 1] if index + 1 < length else ""

        if char == "-" and following == "-":
            output.extend("  ")
            index += 2
            while index < length and sql[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue

        if char == "/" and following == "*":
            output.extend("  ")
            index += 2
            while index + 1 < length and not (
                sql[index] == "*" and sql[index + 1] == "/"
            ):
                output.append(" ")
                index += 1
            if index + 1 >= length:
                raise UnsafeQueryError("SQL contains an unterminated block comment.")
            output.extend("  ")
            index += 2
            continue

        if char in {"'", '"'}:
            quote = char
            output.append(" ")
            index += 1
            while index < length:
                output.append(" ")
                if sql[index] == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        output.append(" ")
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise UnsafeQueryError("SQL contains an unterminated quoted value.")
            continue

        output.append(char)
        index += 1

    return "".join(output)


def _validate_read_only_sql(sql: str) -> None:
    if not isinstance(sql, str):
        raise TypeError("sql must be a string.")
    if not sql.strip():
        raise UnsafeQueryError("SQL query cannot be empty.")

    masked_sql = _mask_literals_identifiers_and_comments(sql)
    statement = masked_sql.strip()

    # Permit one optional trailing semicolon, but reject stacked statements.
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if ";" in statement:
        raise UnsafeQueryError("Multiple SQL statements are not allowed.")

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", statement.upper())
    if not tokens or tokens[0] not in _ALLOWED_START_KEYWORDS:
        raise UnsafeQueryError("Only SELECT queries and read-only WITH queries are allowed.")

    forbidden = sorted(set(tokens).intersection(_FORBIDDEN_KEYWORDS))
    if forbidden:
        raise UnsafeQueryError(
            "Query contains prohibited SQL keyword(s): " + ", ".join(forbidden)
        )


def execute_query(sql: str) -> dict[str, Any]:
    """Execute one read-only analytical query and return columns and rows.

    Args:
        sql: An already-generated DuckDB SELECT statement or read-only WITH query.

    Returns:
        A dictionary with ``columns`` as a list of names and ``rows`` as a list
        of tuples.

    Raises:
        UnsafeQueryError: If the SQL violates the read-only query policy.
        DatabaseQueryError: If DuckDB rejects or cannot execute the safe query.
    """

    _validate_read_only_sql(sql)

    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = duckdb.connect(str(DATABASE_PATH), read_only=True)
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        return {"columns": columns, "rows": rows}
    except duckdb.Error as error:
        raise DatabaseQueryError(f"DuckDB query failed: {error}") from error
    finally:
        if connection is not None:
            connection.close()
