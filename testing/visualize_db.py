#!/usr/bin/env python3
"""
CLI tool to visualize tables in a SQLite database compatible with utils.db_management.DBManager.
Shows schema, row counts, and sample data with optional limits and table selection.
"""

import argparse
import os
import sys

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.text import Text


def get_default_db_path() -> str:
    """Default DB path relative to project root (same as app.py)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "databases", "database.db")


def get_tables(conn: sqlite3.Connection) -> list[str]:
    """Return list of user table names (exclude sqlite_*)."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row[0] for row in cur.fetchall() if not row[0].startswith("sqlite_")]


def get_table_info(conn: sqlite3.Connection, table: str) -> list[tuple]:
    """Return PRAGMA table_info for a table."""
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


def get_row_count(conn: sqlite3.Connection, table: str) -> int:
    """Return number of rows in table."""
    return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]


def get_sample_rows(
    conn: sqlite3.Connection, table: str, limit: int, max_cols: int | None = None
) -> tuple[list[str], list[tuple]]:
    """Return (column_names, rows) for up to `limit` rows. If max_cols, only first max_cols columns."""
    info = get_table_info(conn, table)
    cols = [row[1] for row in info]
    if max_cols is not None and len(cols) > max_cols:
        cols = cols[:max_cols]
    cols_quoted = ", ".join(f'[{c}]' for c in cols)
    cur = conn.execute(f"SELECT {cols_quoted} FROM [{table}] LIMIT ?", (limit,))
    return cols, cur.fetchall()


def truncate(val, max_len: int = 40) -> str:
    """Stringify and truncate for display."""
    s = "" if val is None else str(val)
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def render_schema_table(console: Console, conn: sqlite3.Connection, table: str) -> None:
    """Print schema (columns + types) as a Rich table."""
    info = get_table_info(conn, table)
    if not info:
        return
    schema_table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    schema_table.add_column("cid", style="dim")
    schema_table.add_column("name")
    schema_table.add_column("type")
    schema_table.add_column("notnull")
    schema_table.add_column("default", max_width=20)
    schema_table.add_column("pk")
    for row in info:
        cid, name, type_, notnull, default, pk = row
        schema_table.add_row(
            str(cid),
            name,
            type_ or "",
            str(notnull),
            truncate(default, 20) if default is not None else "",
            str(pk),
        )
    console.print(schema_table)


def render_data_table(
    console: Console,
    conn: sqlite3.Connection,
    table: str,
    limit: int,
    max_cell: int = 36,
    max_cols: int | None = None,
) -> None:
    """Print sample rows as a Rich table with truncated cells."""
    info = get_table_info(conn, table)
    if not info:
        return
    total_cols = len(info)
    cols, rows = get_sample_rows(conn, table, limit, max_cols)
    if not rows:
        console.print("[dim]No rows.[/dim]")
        return
    data_table = Table(show_header=True, header_style="bold green", box=box.ROUNDED)
    for col in cols:
        data_table.add_column(truncate(col, max_cell), max_width=max_cell, overflow="ellipsis")
    for row in rows:
        data_table.add_row(*[truncate(c, max_cell) for c in row])
    console.print(data_table)
    total = get_row_count(conn, table)
    hints = []
    if total > limit:
        hints.append(f"rows: {limit} of {total} (use --limit to change)")
    if max_cols is not None and total_cols > max_cols:
        hints.append(f"columns: first {max_cols} of {total_cols} (use --max-cols to change)")
    if hints:
        console.print("[dim]" + "  |  ".join(hints) + "[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize tables in a DB (schema + sample rows). Compatible with utils.db_management."
    )
    parser.add_argument(
        "--db_path",
        type=str,
        default=None,
        help="Path to SQLite DB (default: databases/database.db under project root)",
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="Show only this table (default: all tables)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max rows to show per table (default: 10)",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Show only schema, no data",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Show only data, no schema",
    )
    parser.add_argument(
        "--max-cell",
        type=int,
        default=36,
        help="Max characters per cell (default: 36)",
    )
    parser.add_argument(
        "--max-cols",
        type=int,
        default=10,
        metavar="N",
        help="Max columns to show in data view (default: 10). Use 0 for all.",
    )
    args = parser.parse_args()
    max_cols = None if args.max_cols == 0 else args.max_cols

    db_path = args.db_path or get_default_db_path()
    if not os.path.isabs(db_path):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.normpath(os.path.join(root, db_path))

    if not os.path.exists(db_path):
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    console = Console()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        tables = get_tables(conn)
        if not tables:
            console.print("[yellow]No user tables in database.[/yellow]")
            return
        if args.table:
            if args.table not in tables:
                console.print(f"[red]Table not found: {args.table}[/red]")
                sys.exit(1)
            tables = [args.table]

        console.print(Panel(f"[bold]{db_path}[/bold]", title="Database", border_style="blue"))

        for table in tables:
            count = get_row_count(conn, table)
            title = f"Table: [bold]{table}[/bold]  —  {count} row(s)"
            console.print()
            console.print(Panel(title, border_style="cyan", padding=(0, 1)))

            if not args.no_schema:
                console.print("[bold]Schema[/bold]")
                render_schema_table(console, conn, table)
                if not args.schema_only:
                    console.print()

            if not args.schema_only:
                console.print("[bold]Sample data[/bold]")
                render_data_table(
                    console, conn, table, args.limit, args.max_cell, max_cols
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
