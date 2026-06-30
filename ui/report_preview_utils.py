"""HTML helpers for report preview dialogs."""

from __future__ import annotations

from html import escape
from typing import Iterable, Sequence

from PySide6.QtWidgets import QTableWidget


def build_report_html(
    title: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    subtitle: str = "",
    summary_lines: Sequence[str] | None = None,
) -> str:
    """Build a printable HTML report document from table-like values."""
    safe_title = escape(str(title or "Report"))
    safe_subtitle = escape(str(subtitle or ""))
    summary_html = "".join(
        f"<div>{escape(str(line))}</div>"
        for line in (summary_lines or [])
        if str(line or "").strip()
    )
    header_html = "".join(f"<th>{escape(str(header or ''))}</th>" for header in headers)
    body_html = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(value or ''))}</td>" for value in row)
        body_html.append(f"<tr>{cells}</tr>")

    if not body_html:
        colspan = max(1, len(headers))
        body_html.append(f"<tr><td colspan='{colspan}'>No data available.</td></tr>")

    return f"""
    <html>
    <head>
        <style>
            body {{
                color: #111827;
                font-family: Arial, sans-serif;
                font-size: 10pt;
                margin: 18px;
            }}
            h1 {{
                color: #1d4ed8;
                font-size: 18pt;
                margin: 0 0 4px 0;
            }}
            .subtitle {{
                color: #374151;
                font-size: 10pt;
                margin-bottom: 8px;
            }}
            .summary {{
                color: #111827;
                margin-bottom: 12px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
            }}
            th {{
                background: #1d4ed8;
                border: 1px solid #93c5fd;
                color: white;
                font-weight: bold;
                padding: 6px;
                text-align: left;
            }}
            td {{
                border: 1px solid #d1d5db;
                padding: 5px;
                vertical-align: top;
            }}
            tr:nth-child(even) td {{
                background: #f8fafc;
            }}
        </style>
    </head>
    <body>
        <h1>{safe_title}</h1>
        <div class="subtitle">{safe_subtitle}</div>
        <div class="summary">{summary_html}</div>
        <table>
            <thead><tr>{header_html}</tr></thead>
            <tbody>{''.join(body_html)}</tbody>
        </table>
    </body>
    </html>
    """


def table_widget_to_html(
    table: QTableWidget,
    title: str,
    subtitle: str = "",
    summary_lines: Sequence[str] | None = None,
) -> str:
    """Build printable HTML from the currently visible rows in a QTableWidget."""
    headers = []
    for column in range(table.columnCount()):
        header = table.horizontalHeaderItem(column)
        headers.append(header.text() if header else "")

    rows = []
    for row in range(table.rowCount()):
        if table.isRowHidden(row):
            continue
        rows.append([
            table.item(row, column).text() if table.item(row, column) else ""
            for column in range(table.columnCount())
        ])

    return build_report_html(title, headers, rows, subtitle, summary_lines)