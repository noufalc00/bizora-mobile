"""Shared helpers for user-resizable table columns (Sales Book style)."""

from __future__ import annotations

from typing import Mapping, Sequence

from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget

from ui.theme import read_only_report_table_style


REPORT_COMPACT_ROW_HEIGHT = 28


def apply_compact_report_table_rows(
    table: QTableWidget,
    *,
    row_height: int = REPORT_COMPACT_ROW_HEIGHT,
) -> None:
    """Apply a standard compact row height for dense read-only report grids."""
    if table is None:
        return
    table.setCornerButtonEnabled(False)
    vertical_header = table.verticalHeader()
    vertical_header.setDefaultSectionSize(row_height)
    vertical_header.setMinimumSectionSize(row_height)
    vertical_header.setMaximumSectionSize(row_height)
    for row_index in range(table.rowCount()):
        table.setRowHeight(row_index, row_height)


def apply_adjustable_table_columns(
    table: QTableWidget,
    *,
    stretch_columns: Sequence[int] | None = None,
    fixed_columns: Mapping[int, int] | None = None,
    auto_size: bool = True,
    sl_no_column: int | None = None,
    sl_no_width: int = 60,
    min_width: int = 48,
) -> None:
    """Enable drag-to-resize columns like Sales Book."""
    if table is None or table.columnCount() <= 0:
        return

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(min_width)
    header.setHighlightSections(True)
    header.setSectionsClickable(True)

    stretch_set = set(stretch_columns or ())
    fixed_map = dict(fixed_columns or {})
    column_count = table.columnCount()

    for column_index in range(column_count):
        if column_index in fixed_map:
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Fixed)
        elif column_index in stretch_set:
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Interactive)

    if auto_size:
        table.resizeColumnsToContents()

    if sl_no_column is not None and 0 <= sl_no_column < column_count:
        header.setSectionResizeMode(sl_no_column, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(sl_no_column, sl_no_width)

    for column_index, width in fixed_map.items():
        if 0 <= column_index < column_count:
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(column_index, width)


def finalize_report_table_layout(
    table: QTableWidget,
    *,
    sl_no_column: int | None = None,
    sl_no_width: int = 60,
    min_width: int = 48,
) -> None:
    """Apply Sales-Book column resizing without stretch/fixed locks."""
    apply_adjustable_table_columns(
        table,
        sl_no_column=sl_no_column,
        sl_no_width=sl_no_width,
        min_width=min_width,
        auto_size=False,
    )


def apply_read_only_report_table_selection(
    table: QTableWidget,
    *,
    hide_vertical_header: bool = True,
    extra_stylesheet: str = "",
) -> None:
    """Apply standard read-only report/book row selection and styling."""
    if table is None:
        return

    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setCornerButtonEnabled(False)
    if hide_vertical_header:
        table.verticalHeader().setVisible(False)

    stylesheet = read_only_report_table_style()
    if extra_stylesheet.strip():
        stylesheet = f"{stylesheet}\n{extra_stylesheet.strip()}"
    table.setStyleSheet(stylesheet)