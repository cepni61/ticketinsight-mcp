"""TicketInsight MCP server.

Exposes the IT support ticket SQLite database (data/tickets.db) through the
Model Context Protocol using FastMCP. Ad-hoc querying (run_query) is strictly
read-only; creating and updating tickets is only possible through the
dedicated, validated create_ticket and update_ticket tools.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

DB_PATH = Path(__file__).parent / "data" / "tickets.db"
MAX_ROWS = 200

FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "ATTACH",
    "DETACH",
    "REPLACE",
    "CREATE",
    "PRAGMA",
    "VACUUM",
)

VALID_PRIORITIES: tuple[str, ...] = ("Low", "Medium", "High", "Critical")
VALID_STATUSES: tuple[str, ...] = ("Open", "In Progress", "Resolved", "Closed")
RESOLVED_STATUSES: tuple[str, ...] = ("Resolved", "Closed")

mcp = FastMCP("TicketInsight")


def _get_connection() -> sqlite3.Connection:
    """Open a read-only connection to the tickets database."""
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _get_write_connection() -> sqlite3.Connection:
    """Open a read-write connection to the tickets database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@mcp.tool()
def list_tables() -> list[str]:
    """List all table names available in the tickets database."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]
    except sqlite3.Error as exc:
        return [f"Error listing tables: {exc}"]
    finally:
        conn.close()


@mcp.tool()
def get_schema(table_name: str) -> str:
    """Return the CREATE TABLE statement for the given table.

    Args:
        table_name: Name of the table to inspect.
    """
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if row is None:
            return f"Error: table '{table_name}' was not found."
        return row["sql"]
    except sqlite3.Error as exc:
        return f"Error retrieving schema for '{table_name}': {exc}"
    finally:
        conn.close()


@mcp.tool()
def run_query(sql: str) -> list[dict[str, Any]] | dict[str, str]:
    """Run a read-only SQL SELECT query against the tickets database.

    Only SELECT statements are permitted. The query must start with SELECT
    and must not contain data-modifying or schema-altering keywords. Results
    are capped at 200 rows.

    Args:
        sql: The SQL SELECT statement to execute.
    """
    stripped = sql.strip()
    normalized = stripped.upper()

    if not normalized.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed."}

    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            return {"error": f"Query contains forbidden keyword: {keyword}."}

    conn = _get_connection()
    try:
        cursor = conn.execute(stripped)
        rows = cursor.fetchmany(MAX_ROWS)
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        return {"error": f"Query failed: {exc}"}
    finally:
        conn.close()


@mcp.tool()
def get_sample_rows(table_name: str, limit: int = 5) -> list[dict[str, Any]] | dict[str, str]:
    """Return a small sample of rows from the given table.

    Args:
        table_name: Name of the table to sample.
        limit: Maximum number of rows to return (capped at 200).
    """
    capped_limit = max(1, min(limit, MAX_ROWS))
    conn = _get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if table_name not in tables:
            return {"error": f"Table '{table_name}' was not found."}

        cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (capped_limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        return {"error": f"Failed to sample table '{table_name}': {exc}"}
    finally:
        conn.close()


@mcp.tool()
def create_ticket(
    title: str,
    category_id: int,
    priority: str,
    requester: str,
    assigned_to: int,
    status: str = "Open",
) -> dict[str, Any]:
    """Create a new support ticket.

    Args:
        title: Short description of the issue.
        category_id: ID of an existing category.
        priority: One of Low, Medium, High, Critical.
        requester: Name of the person reporting the issue.
        assigned_to: ID of an existing agent.
        status: One of Open, In Progress, Resolved, Closed. Defaults to Open.
    """
    if not title.strip():
        return {"error": "Title must not be empty."}
    if priority not in VALID_PRIORITIES:
        return {"error": f"Invalid priority. Must be one of: {', '.join(VALID_PRIORITIES)}."}
    if status not in VALID_STATUSES:
        return {"error": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}."}
    if not requester.strip():
        return {"error": "Requester must not be empty."}

    conn = _get_write_connection()
    try:
        if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
            return {"error": f"category_id {category_id} does not exist."}
        if conn.execute("SELECT 1 FROM agents WHERE id = ?", (assigned_to,)).fetchone() is None:
            return {"error": f"assigned_to {assigned_to} does not exist."}

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resolved_at = created_at if status in RESOLVED_STATUSES else None

        cursor = conn.execute(
            """
            INSERT INTO tickets (
                title, category_id, priority, status, requester,
                assigned_to, created_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, category_id, priority, status, requester, assigned_to, created_at, resolved_at),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    except sqlite3.Error as exc:
        return {"error": f"Failed to create ticket: {exc}"}
    finally:
        conn.close()


@mcp.tool()
def update_ticket(
    ticket_id: int,
    title: str | None = None,
    category_id: int | None = None,
    priority: str | None = None,
    status: str | None = None,
    assigned_to: int | None = None,
) -> dict[str, Any]:
    """Update one or more fields on an existing ticket.

    Only the fields provided are changed. When status is set to Resolved or
    Closed and the ticket has no resolved_at timestamp yet, it is stamped
    with the current time; moving back to Open or In Progress clears it.

    Args:
        ticket_id: ID of the ticket to update.
        title: New title, if changing.
        category_id: New category ID, if changing.
        priority: New priority (Low, Medium, High, Critical), if changing.
        status: New status (Open, In Progress, Resolved, Closed), if changing.
        assigned_to: New agent ID, if changing.
    """
    if title is not None and not title.strip():
        return {"error": "Title must not be empty."}
    if priority is not None and priority not in VALID_PRIORITIES:
        return {"error": f"Invalid priority. Must be one of: {', '.join(VALID_PRIORITIES)}."}
    if status is not None and status not in VALID_STATUSES:
        return {"error": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}."}

    conn = _get_write_connection()
    try:
        existing = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if existing is None:
            return {"error": f"Ticket {ticket_id} does not exist."}

        if category_id is not None and conn.execute(
            "SELECT 1 FROM categories WHERE id = ?", (category_id,)
        ).fetchone() is None:
            return {"error": f"category_id {category_id} does not exist."}
        if assigned_to is not None and conn.execute(
            "SELECT 1 FROM agents WHERE id = ?", (assigned_to,)
        ).fetchone() is None:
            return {"error": f"assigned_to {assigned_to} does not exist."}

        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if category_id is not None:
            updates["category_id"] = category_id
        if priority is not None:
            updates["priority"] = priority
        if assigned_to is not None:
            updates["assigned_to"] = assigned_to
        if status is not None:
            updates["status"] = status
            if status in RESOLVED_STATUSES and existing["resolved_at"] is None:
                updates["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif status not in RESOLVED_STATUSES:
                updates["resolved_at"] = None

        if not updates:
            return {"error": "No fields provided to update."}

        # Column names come only from the fixed whitelist built above, never
        # from caller-supplied strings, so this is not injectable.
        set_clause = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE tickets SET {set_clause} WHERE id = ?",
            (*updates.values(), ticket_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row)
    except sqlite3.Error as exc:
        return {"error": f"Failed to update ticket: {exc}"}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
