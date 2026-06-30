from typing import Any, Dict, List, Optional
from decimal import Decimal
import traceback
from PySide6.QtCore import Qt, QDate, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFrame, QGroupBox, QMessageBox
from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis, QLineSeries
from db import Database
from bizora_core.monthly_analysis_logic import MonthlyAnalysisLogic
from ui.table_header_utils import apply_read_only_report_table_selection
from ui.checkbox_style import create_checkbox
from ui.book_report_common import compact_label_style, compact_input_style, compact_combo_style, compact_primary_button_style, compact_secondary_button_style, page_background_style, report_data_table_style, report_filter_frame_style, report_page_shell_style, _report_theme_colors
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin
from ui import theme
from config import CURRENCY_SYMBOL
from utils.financial_year import (
    get_current_financial_year_label,
    get_financial_year_options,
    get_working_financial_year_label,
)

def compact_topbar_frame_style() -> str:
    """Compact topbar frame style."""
    return report_filter_frame_style()

def _metric_chip_style(color: str) -> str:
    c = _report_theme_colors()
    return f"color: {color}; font-weight: bold; padding: 6px 12px; background: {c['panel_bg']}; border: 1px solid {c['border']}; border-radius: 6px;"

def _chart_colors() -> dict:
    """Theme-aware chart palette for monthly analysis visuals."""
    return theme.chart_palette()


def _chart_accent_hex() -> str:
    """Accent color for chart titles and emphasis rows."""
    return _report_theme_colors()["accent_label"]

class MonthlyAnalysisWorker(QObject):
    """Load monthly ledger analysis on a worker-owned database connection."""
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, db_type, db_path, company_id, start_date, end_date, from_month, to_month):
        """Initialize worker with immutable monthly analysis inputs."""
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.start_date = start_date
        self.end_date = end_date
        self.from_month = from_month
        self.to_month = to_month

    def run(self):
        """Fetch monthly analysis outside the GUI thread."""
        worker_db = None
        try:
            self.progress.emit('Loading verified ledger analysis...')
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = MonthlyAnalysisLogic(worker_db)
            result = logic.get_monthly_analysis(self.company_id, self.start_date, self.end_date, self.from_month, self.to_month)
            if not result.get('success'):
                self.error.emit(result.get('message', 'Unable to load monthly analysis.'))
                return
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                try:
                    worker_db.force_disconnect()
                except Exception:
                    pass

class MonthlyAnalysisWidget(UiMemoryMixin, QWidget):
    """Monthly Analysis page - read-only business analysis module."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.logic = MonthlyAnalysisLogic(self.db)
        self.company_id = None
        self.current_data = []
        self._analysis_thread = None
        self._analysis_worker = None
        self._loading = False
        self._build_ui()
        self._init_ui_memory(table_attrs=())
        QTimer.singleShot(0, self.refresh)

    def _prepare_table_for_layout_change(self) -> None:
        """Clear table content without resetting column count to zero (Qt crash guard)."""
        self.table.clearSpans()
        self.table.clearContents()
        self.table.setRowCount(0)

    def _stop_analysis_worker(self) -> None:
        """Disconnect callbacks from any in-flight analysis worker thread."""
        worker = self._analysis_worker
        thread = self._analysis_thread
        self._analysis_thread = None
        self._analysis_worker = None
        if worker is not None:
            try:
                worker.finished.disconnect()
                worker.error.disconnect()
            except Exception:
                pass
        if thread is not None:
            try:
                thread.started.disconnect()
                thread.finished.disconnect()
            except Exception:
                pass
            if thread.isRunning():
                thread.quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Stop background work before the widget is closed."""
        self._stop_analysis_worker()
        super().closeEvent(event)

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(self.page_style())
        if hasattr(self, 'filter_frame'):
            self.filter_frame.setStyleSheet(report_filter_frame_style('QFrame#filterFrame'))
        if hasattr(self, 'summary_frame'):
            self.summary_frame.setStyleSheet(report_filter_frame_style())
        if hasattr(self, 'percentage_frame'):
            self.percentage_frame.setStyleSheet(report_filter_frame_style())
        for combo_name in ('analysis_type_combo', 'fy_combo', 'from_month_combo', 'to_month_combo'):
            combo = getattr(self, combo_name, None)
            if combo is not None:
                combo.setStyleSheet(compact_combo_style())
        if hasattr(self, 'generate_btn'):
            self.generate_btn.setStyleSheet(compact_primary_button_style())
        if hasattr(self, 'open_chart_btn'):
            self.open_chart_btn.setStyleSheet(compact_secondary_button_style())
        if hasattr(self, 'table'):
            apply_read_only_report_table_selection(
                self.table,
                extra_stylesheet=report_data_table_style(),
            )

    def page_style(self) -> str:
        """Page stylesheet."""
        c = _report_theme_colors()
        return report_page_shell_style('MonthlyAnalysisWidget') + f" QFrame#filterFrame {{ background-color: {c['panel_bg']}; border: 1px solid {c['border']}; border-radius: 6px; }}" + f" QLabel {{ color: {c['label_text']}; background: transparent; }}"

    def _build_ui(self):
        """Build UI components."""
        self.setObjectName('MonthlyAnalysisWidget')
        self.setStyleSheet(self.page_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        filter_frame = QFrame()
        self.filter_frame = filter_frame
        filter_frame.setObjectName('filterFrame')
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(15)
        analysis_type_label = QLabel('Analysis Type')
        analysis_type_label.setStyleSheet(compact_label_style())
        self.analysis_type_combo = QComboBox()
        self.analysis_type_combo.addItems(['All', 'Trading Income', 'Direct Expenses', 'Indirect Income', 'Indirect Expenses', 'Net Profit'])
        self.analysis_type_combo.setStyleSheet(compact_combo_style())
        self.analysis_type_combo.setFixedWidth(110)
        self.analysis_type_combo.currentTextChanged.connect(self.refresh)
        fy_label = QLabel('Financial Year')
        fy_label.setStyleSheet(compact_label_style())
        self.fy_combo = QComboBox()
        self._populate_financial_year_combo()
        self.fy_combo.setStyleSheet(compact_combo_style())
        self.fy_combo.setFixedWidth(80)
        from_month_label = QLabel('From Month')
        from_month_label.setStyleSheet(compact_label_style())
        self.from_month_combo = QComboBox()
        self.from_month_combo.addItems(['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March'])
        self.from_month_combo.setStyleSheet(compact_combo_style())
        self.from_month_combo.setFixedWidth(90)
        to_month_label = QLabel('To Month')
        to_month_label.setStyleSheet(compact_label_style())
        self.to_month_combo = QComboBox()
        self.to_month_combo.addItems(['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March'])
        self.to_month_combo.setStyleSheet(compact_combo_style())
        self.to_month_combo.setFixedWidth(90)
        self.to_month_combo.setCurrentText('March')
        self.refresh_btn = QPushButton('Refresh')
        self.refresh_btn.setStyleSheet(compact_primary_button_style())
        self.refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(analysis_type_label)
        filter_layout.addWidget(self.analysis_type_combo)
        filter_layout.addWidget(fy_label)
        filter_layout.addWidget(self.fy_combo)
        filter_layout.addWidget(from_month_label)
        filter_layout.addWidget(self.from_month_combo)
        filter_layout.addWidget(to_month_label)
        filter_layout.addWidget(self.to_month_combo)
        filter_layout.addStretch()
        filter_layout.addWidget(self.refresh_btn)
        layout.addWidget(filter_frame)
        summary_frame = QFrame()
        self.summary_frame = summary_frame
        summary_frame.setStyleSheet(report_filter_frame_style())
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(10)
        self.total_sales_label = self.summary_label(self._summary_placeholder('Trading Income'))
        self.total_sales_return_label = self.summary_label(self._summary_placeholder('Direct Expenses'))
        self.net_sales_label = self.summary_label(self._summary_placeholder('Gross Profit'))
        self.total_purchase_label = self.summary_label(self._summary_placeholder('Indirect Income'))
        self.total_purchase_return_label = self.summary_label(self._summary_placeholder('Indirect Expenses'))
        self.net_purchase_label = self.summary_label(self._summary_placeholder('Net Profit'))
        summary_layout.addWidget(self.total_sales_label)
        summary_layout.addWidget(self.total_sales_return_label)
        summary_layout.addWidget(self.net_sales_label)
        summary_layout.addWidget(self.total_purchase_label)
        summary_layout.addWidget(self.total_purchase_return_label)
        summary_layout.addWidget(self.net_purchase_label)
        summary_layout.addStretch()
        layout.addWidget(summary_frame)
        percentage_frame = QFrame()
        self.percentage_frame = percentage_frame
        percentage_frame.setStyleSheet(report_filter_frame_style())
        percentage_layout = QHBoxLayout(percentage_frame)
        percentage_layout.setContentsMargins(10, 8, 10, 8)
        percentage_layout.setSpacing(10)
        self.sales_percent_label = self.percentage_label('Gross Profit %: 0.00%')
        self.sales_return_percent_label = self.percentage_label('Net Profit %: 0.00%')
        self.purchase_percent_label = self.percentage_label('Indirect Income %: 0.00%')
        self.purchase_return_percent_label = self.percentage_label('Indirect Expense %: 0.00%')
        percentage_layout.addWidget(self.sales_percent_label)
        percentage_layout.addWidget(self.sales_return_percent_label)
        percentage_layout.addWidget(self.purchase_percent_label)
        percentage_layout.addWidget(self.purchase_return_percent_label)
        percentage_layout.addStretch()
        self.open_chart_btn = QPushButton('Open Chart')
        self.open_chart_btn.setStyleSheet(compact_secondary_button_style())
        self.open_chart_btn.clicked.connect(self.open_chart_in_window)
        percentage_layout.addWidget(self.open_chart_btn)
        layout.addWidget(percentage_frame)
        self.table = QTableWidget()
        apply_read_only_report_table_selection(
            self.table,
            extra_stylesheet=report_data_table_style(),
        )
        layout.addWidget(self.table, 1)

    def _populate_financial_year_combo(self) -> None:
        """Fill FY filter with current/past years and select the active FY."""
        options = list(get_financial_year_options(years_before_current=3))
        current_label = get_current_financial_year_label()
        start_year = int(current_label.split('-')[0])
        for offset in range(1, 3):
            future_label = f"{start_year + offset}-{str(start_year + offset + 1)[-2:]}"
            if future_label not in options:
                options.append(future_label)
        self.fy_combo.addItems(options)
        default_fy = get_working_financial_year_label() or current_label
        if default_fy in options:
            self.fy_combo.setCurrentText(default_fy)
        else:
            self.fy_combo.setCurrentText(current_label)

    def _summary_placeholder(self, label: str) -> str:
        """Build a zero-value summary chip label using the app currency symbol."""
        return f"{label}: {self.format_currency(Decimal('0'))}"

    def summary_label(self, text: str) -> QLabel:
        """Create summary label."""
        item = QLabel(text)
        item.setStyleSheet(_metric_chip_style(_report_theme_colors()['input_text']))
        return item

    def percentage_label(self, text: str) -> QLabel:
        """Create percentage label."""
        item = QLabel(text)
        item.setStyleSheet(_metric_chip_style(_chart_accent_hex()))
        return item

    def refresh(self):
        """Refresh the report."""
        if self._loading:
            return
        try:
            from config import active_company_manager
            self.company_id = active_company_manager.get_active_company_id()
            if not self.company_id:
                self.show_no_data('Please open a company first.')
                return
            self.company_id = int(self.company_id)
        except Exception as e:
            self.show_no_data(f'Error loading company: {str(e)}')
            return
        analysis_type = self.analysis_type_combo.currentText()
        financial_year = self.fy_combo.currentText()
        from_month = self.from_month_combo.currentText()
        to_month = self.to_month_combo.currentText()
        print(f'[DEBUG] Monthly Analysis Refresh - Type: {analysis_type}, FY: {financial_year}, From: {from_month}, To: {to_month}')
        try:
            start_date, end_date = self.logic.get_financial_year_range(financial_year, from_month, to_month)
        except Exception as e:
            self.show_no_data(f'Error calculating date range: {str(e)}')
            return
        thread = QThread(self)
        worker = MonthlyAnalysisWorker(getattr(self.db, 'db_type', None), getattr(self.db, 'db_path', None), self.company_id, start_date, end_date, from_month, to_month)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result, selected=analysis_type: self._on_analysis_ready(result, selected))
        worker.finished.connect(thread.quit)
        worker.error.connect(self._on_analysis_error)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_analysis_worker_finished)
        self._analysis_thread = thread
        self._analysis_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _on_analysis_ready(self, result: Dict[str, Any], analysis_type: str):
        """Queue analysis rendering on the next GUI event-loop tick."""
        QTimer.singleShot(0, lambda: self._apply_analysis_result(result, analysis_type))

    def _apply_analysis_result(self, result: Dict[str, Any], analysis_type: str) -> None:
        """Apply worker-calculated monthly analysis on the GUI thread."""
        try:
            if not result.get('success'):
                self.show_no_data(result.get('message', 'Error loading data'))
                return
            data = result.get('data', [])
            summary = result.get('summary', {})
            self.update_summary(summary)
            self.update_percentages(summary)
            self.populate_table(data, analysis_type)
            self.current_data = data
            self.update_chart(data)
            print(f'[DEBUG] Monthly Analysis table ready: {len(data)} rows')
        except Exception as exc:
            print(f'[ERROR] Monthly Analysis display failed: {exc}')
            traceback.print_exc()
            self.show_no_data(f'Error displaying report: {exc}')

    def _on_analysis_error(self, message: str):
        """Display worker errors and keep the page responsive."""
        self.show_no_data(f'Error loading data: {message}')

    def _on_analysis_progress(self, message: str):
        """Reserved for future status updates; table loading is handled once in refresh()."""
        _ = message

    def _on_analysis_worker_finished(self):
        """Restore controls after monthly analysis worker exits."""
        self._analysis_thread = None
        self._analysis_worker = None
        self._set_loading_state(False)

    def _set_loading_state(self, is_loading: bool):
        """Disable report controls while the worker calculates."""
        self._loading = is_loading
        controls = [self.refresh_btn, self.analysis_type_combo, self.fy_combo, self.from_month_combo, self.to_month_combo, self.open_chart_btn]
        for control in controls:
            control.setEnabled(not is_loading)
        self.refresh_btn.setText('Loading...' if is_loading else 'Refresh')
        if is_loading:
            self.current_data = []
            self.show_loading('Loading verified ledger analysis...')

    def update_summary(self, summary: Dict[str, Decimal]):
        """Update summary labels."""
        trading_income = summary.get('trading_income', Decimal('0'))
        direct_expenses = summary.get('direct_expenses', Decimal('0'))
        gross_profit = summary.get('gross_profit', Decimal('0'))
        indirect_income = summary.get('indirect_income', Decimal('0'))
        indirect_expenses = summary.get('indirect_expenses', Decimal('0'))
        net_profit = summary.get('net_profit', Decimal('0'))
        self.total_sales_label.setText(f'Trading Income: {self.format_currency(trading_income)}')
        self.total_sales_return_label.setText(f'Direct Expenses: {self.format_currency(direct_expenses)}')
        self.net_sales_label.setText(f'Gross Profit: {self.format_currency(gross_profit)}')
        self.total_purchase_label.setText(f'Indirect Income: {self.format_currency(indirect_income)}')
        self.total_purchase_return_label.setText(f'Indirect Expenses: {self.format_currency(indirect_expenses)}')
        self.net_purchase_label.setText(f'Net Profit: {self.format_currency(net_profit)}')
        self.total_sales_label.setStyleSheet(_metric_chip_style(_chart_colors()['positive']))
        self.net_sales_label.setStyleSheet(_metric_chip_style(_chart_colors()['positive']))
        self.total_sales_return_label.setStyleSheet(_metric_chip_style(_chart_colors()['negative']))
        self.total_purchase_return_label.setStyleSheet(_metric_chip_style(_chart_colors()['negative']))

    def update_percentages(self, summary: Dict[str, Decimal]):
        """Update percentage labels with safe calculations."""
        trading_income = summary.get('trading_income', Decimal('0'))
        direct_expenses = summary.get('direct_expenses', Decimal('0'))
        indirect_income = summary.get('indirect_income', Decimal('0'))
        indirect_expenses = summary.get('indirect_expenses', Decimal('0'))
        gross_profit = summary.get('gross_profit', Decimal('0'))
        net_profit = summary.get('net_profit', Decimal('0'))
        if trading_income > Decimal('0'):
            gross_profit_percent = gross_profit / trading_income * Decimal('100')
            net_profit_percent = net_profit / trading_income * Decimal('100')
        else:
            gross_profit_percent = Decimal('0')
            net_profit_percent = Decimal('0')
        total_turnover = trading_income + direct_expenses
        if total_turnover > Decimal('0'):
            indirect_income_percent = indirect_income / total_turnover * Decimal('100')
            indirect_expense_percent = indirect_expenses / total_turnover * Decimal('100')
        else:
            indirect_income_percent = Decimal('0')
            indirect_expense_percent = Decimal('0')
        self.sales_percent_label.setText(f'Gross Profit %: {gross_profit_percent:.2f}%')
        self.sales_return_percent_label.setText(f'Net Profit %: {net_profit_percent:.2f}%')
        self.purchase_percent_label.setText(f'Indirect Income %: {indirect_income_percent:.2f}%')
        self.purchase_return_percent_label.setText(f'Indirect Expense %: {indirect_expense_percent:.2f}%')
        print(f'[DEBUG] Percentages - Gross Profit %: {gross_profit_percent}, Net Profit %: {net_profit_percent}')

    def update_chart(self, data: List[Dict[str, Any]]):
        """Update chart with existing monthly dataset (NO duplicate DB query)."""
        pass

    def open_chart_in_window(self):
        """Open chart in separate window."""
        if self._loading:
            QMessageBox.information(
                self,
                'Monthly Analysis',
                'Report is still loading. Please wait for it to finish or click Refresh.',
            )
            return
        if not self.current_data:
            QMessageBox.information(
                self,
                'Monthly Analysis',
                'No chart data available. Click Refresh to load the report first.',
            )
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
        chart_window = QDialog(self)
        chart_window.setWindowTitle('Monthly Analysis Chart')
        chart_window.setMinimumSize(800, 500)
        chart_window.setStyleSheet(page_background_style())
        layout = QVBoxLayout(chart_window)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        chart_header_layout = QHBoxLayout()
        chart_header_layout.setSpacing(15)
        chart_type_label = QLabel('Chart Type:')
        chart_type_label.setStyleSheet(compact_label_style())
        chart_header_layout.addWidget(chart_type_label)
        chart_type_combo = QComboBox()
        chart_type_combo.addItems(['All Series', 'Trading vs Direct'])
        chart_type_combo.setStyleSheet(compact_combo_style())
        chart_type_combo.setFixedWidth(140)
        chart_header_layout.addWidget(chart_type_combo)
        viz_type_label = QLabel('View:')
        viz_type_label.setStyleSheet(compact_label_style())
        chart_header_layout.addWidget(viz_type_label)
        viz_type_combo = QComboBox()
        viz_type_combo.addItems(['Bar Chart', 'Line Chart'])
        viz_type_combo.setStyleSheet(compact_combo_style())
        viz_type_combo.setFixedWidth(100)
        chart_header_layout.addWidget(viz_type_combo)
        chart_header_layout.addStretch()
        show_sales_cb = create_checkbox('Trading Income', label_color=_chart_colors()['positive'], font_size=11)
        show_sales_cb.setChecked(True)
        chart_header_layout.addWidget(show_sales_cb)
        show_sales_return_cb = create_checkbox('Gross Profit', label_color=_chart_colors()['negative'], font_size=11)
        show_sales_return_cb.setChecked(True)
        chart_header_layout.addWidget(show_sales_return_cb)
        show_purchase_cb = create_checkbox('Direct Expenses', label_color=_chart_colors()['primary'], font_size=11)
        show_purchase_cb.setChecked(True)
        chart_header_layout.addWidget(show_purchase_cb)
        show_purchase_return_cb = create_checkbox('Net Profit', label_color=_chart_colors()['warning'], font_size=11)
        show_purchase_return_cb.setChecked(True)
        chart_header_layout.addWidget(show_purchase_return_cb)
        svp_show_sales_cb = create_checkbox('Trading Income', label_color=_chart_colors()['positive'], font_size=11)
        svp_show_sales_cb.setChecked(True)
        svp_show_sales_cb.setVisible(False)
        chart_header_layout.addWidget(svp_show_sales_cb)
        svp_show_purchase_cb = create_checkbox('Direct Expenses', label_color=_chart_colors()['primary'], font_size=11)
        svp_show_purchase_cb.setChecked(True)
        svp_show_purchase_cb.setVisible(False)
        chart_header_layout.addWidget(svp_show_purchase_cb)
        layout.addLayout(chart_header_layout)
        chart_view = QChartView()
        chart_view.setRenderHints(QPainter.RenderHint.Antialiasing)
        chart_view.setStyleSheet(report_filter_frame_style('QChartView'))
        layout.addWidget(chart_view)
        chart = self._create_chart(self.current_data, show_sales_cb, show_sales_return_cb, show_purchase_cb, show_purchase_return_cb)
        chart_view.setChart(chart)
        chart_view.setInteractive(False)

        def update_window_chart():
            chart_type = chart_type_combo.currentText()
            viz_type = viz_type_combo.currentText()
            if viz_type == 'Bar Chart':
                if chart_type == 'All Series':
                    show_sales_cb.setVisible(True)
                    show_sales_return_cb.setVisible(True)
                    show_purchase_cb.setVisible(True)
                    show_purchase_return_cb.setVisible(True)
                    svp_show_sales_cb.setVisible(False)
                    svp_show_purchase_cb.setVisible(False)
                    chart = self._create_chart(self.current_data, show_sales_cb, show_sales_return_cb, show_purchase_cb, show_purchase_return_cb)
                else:
                    show_sales_cb.setVisible(False)
                    show_sales_return_cb.setVisible(False)
                    show_purchase_cb.setVisible(False)
                    show_purchase_return_cb.setVisible(False)
                    svp_show_sales_cb.setVisible(True)
                    svp_show_purchase_cb.setVisible(True)
                    chart = self._create_sales_vs_purchase_chart(self.current_data, svp_show_sales_cb, svp_show_purchase_cb)
            elif chart_type == 'All Series':
                show_sales_cb.setVisible(True)
                show_sales_return_cb.setVisible(True)
                show_purchase_cb.setVisible(True)
                show_purchase_return_cb.setVisible(True)
                svp_show_sales_cb.setVisible(False)
                svp_show_purchase_cb.setVisible(False)
                chart = self._create_line_chart(self.current_data, show_sales_cb, show_sales_return_cb, show_purchase_cb, show_purchase_return_cb)
            else:
                show_sales_cb.setVisible(False)
                show_sales_return_cb.setVisible(False)
                show_purchase_cb.setVisible(False)
                show_purchase_return_cb.setVisible(False)
                svp_show_sales_cb.setVisible(True)
                svp_show_purchase_cb.setVisible(True)
                chart = self._create_sales_vs_purchase_line_chart(self.current_data, svp_show_sales_cb, svp_show_purchase_cb)
            chart_view.setChart(chart)
            chart_view.setInteractive(False)
        chart_type_combo.currentTextChanged.connect(update_window_chart)
        viz_type_combo.currentTextChanged.connect(update_window_chart)
        show_sales_cb.stateChanged.connect(update_window_chart)
        show_sales_return_cb.stateChanged.connect(update_window_chart)
        show_purchase_cb.stateChanged.connect(update_window_chart)
        show_purchase_return_cb.stateChanged.connect(update_window_chart)
        svp_show_sales_cb.stateChanged.connect(update_window_chart)
        svp_show_purchase_cb.stateChanged.connect(update_window_chart)
        chart_window.exec()

    def _chart_axis_range(self, data: List[Dict[str, Any]], keys: List[str]) -> tuple:
        """Calculate a padded Y-axis range that keeps losses visible."""
        values = [float(row.get(key, 0) or 0) for row in data for key in keys]
        if not values:
            return (0, 1)
        min_value = min(values)
        max_value = max(values)
        if min_value == max_value:
            padding = abs(max_value) * 0.1 or 1
        else:
            padding = (max_value - min_value) * 0.1
        return (min(0, min_value - padding), max(0, max_value + padding))

    def _create_chart(self, data: List[Dict[str, Any]], show_sales_cb, show_sales_return_cb, show_purchase_cb, show_purchase_return_cb) -> QChart:
        """Create chart from data (reused by window view)."""
        if not data:
            return None
        chart = QChart()
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.setBackgroundVisible(False)
        bar_series = QBarSeries()
        categories = [f"{row['month_name']} {row['year']}" for row in data]
        sales_set = QBarSet('Trading Income')
        sales_set.setColor(QColor(_chart_colors()['positive']))
        sales_return_set = QBarSet('Gross Profit')
        sales_return_set.setColor(QColor(_chart_accent_hex()))
        purchase_set = QBarSet('Direct Expenses')
        purchase_set.setColor(QColor(_chart_colors()['primary']))
        purchase_return_set = QBarSet('Net Profit')
        purchase_return_set.setColor(QColor(_chart_colors()['warning']))
        for row in data:
            sales_set.append(float(row['trading_income']))
            sales_return_set.append(float(row['gross_profit']))
            purchase_set.append(float(row['direct_expenses']))
            purchase_return_set.append(float(row['net_profit']))
        if show_sales_cb.isChecked():
            bar_series.append(sales_set)
        if show_sales_return_cb.isChecked():
            bar_series.append(sales_return_set)
        if show_purchase_cb.isChecked():
            bar_series.append(purchase_set)
        if show_purchase_return_cb.isChecked():
            bar_series.append(purchase_return_set)
        chart.addSeries(bar_series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setTitleText('Month')
        axis_x.setTitleBrush(QColor(_chart_accent_hex()))
        axis_x.setLabelsColor(QColor(_chart_colors()['axis_label']))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        bar_series.attachAxis(axis_x)
        axis_y = QValueAxis()
        min_value, max_value = self._chart_axis_range(data, ['trading_income', 'direct_expenses', 'gross_profit', 'net_profit'])
        axis_y.setRange(min_value, max_value)
        axis_y.setTitleText(f'Amount ({CURRENCY_SYMBOL})')
        axis_y.setTitleBrush(QColor(_chart_accent_hex()))
        axis_y.setLabelsColor(QColor(_chart_colors()['axis_label']))
        axis_y.setGridLineColor(QColor(_chart_colors()['grid_line']))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        bar_series.attachAxis(axis_y)
        chart.setTitle('Monthly Analysis')
        chart.setTitleBrush(QColor(_chart_accent_hex()))
        chart.legend().setLabelColor(QColor(_chart_colors()['legend_text']))
        chart.legend().setBorderColor(QColor(_chart_colors()['grid_line']))
        return chart

    def _create_sales_vs_purchase_chart(self, data: List[Dict[str, Any]], show_sales_cb, show_purchase_cb) -> QChart:
        """Create Sales vs Purchase grouped bar chart from existing data."""
        if not data:
            return None
        chart = QChart()
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.setBackgroundVisible(False)
        bar_series = QBarSeries()
        categories = [f"{row['month_name']} {row['year']}" for row in data]
        sales_set = QBarSet('Trading Income')
        sales_set.setColor(QColor(_chart_colors()['positive']))
        purchase_set = QBarSet('Direct Expenses')
        purchase_set.setColor(QColor(_chart_colors()['primary']))
        for row in data:
            sales_set.append(float(row['trading_income']))
            purchase_set.append(float(row['direct_expenses']))
        if show_sales_cb.isChecked():
            bar_series.append(sales_set)
        if show_purchase_cb.isChecked():
            bar_series.append(purchase_set)
        chart.addSeries(bar_series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setTitleText('Month')
        axis_x.setTitleBrush(QColor(_chart_accent_hex()))
        axis_x.setLabelsColor(QColor(_chart_colors()['axis_label']))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        bar_series.attachAxis(axis_x)
        axis_y = QValueAxis()
        min_value, max_value = self._chart_axis_range(data, ['trading_income', 'direct_expenses'])
        axis_y.setRange(min_value, max_value)
        axis_y.setTitleText(f'Amount ({CURRENCY_SYMBOL})')
        axis_y.setTitleBrush(QColor(_chart_accent_hex()))
        axis_y.setLabelsColor(QColor(_chart_colors()['axis_label']))
        axis_y.setGridLineColor(QColor(_chart_colors()['grid_line']))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        bar_series.attachAxis(axis_y)
        chart.setTitle('Trading Income vs Direct Expenses')
        chart.setTitleBrush(QColor(_chart_accent_hex()))
        chart.legend().setLabelColor(QColor(_chart_colors()['legend_text']))
        chart.legend().setBorderColor(QColor(_chart_colors()['grid_line']))
        return chart

    def _create_line_chart(self, data: List[Dict[str, Any]], show_sales_cb, show_sales_return_cb, show_purchase_cb, show_purchase_return_cb) -> QChart:
        """Create Line Chart from existing data (All Series)."""
        if not data:
            return None
        chart = QChart()
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.setBackgroundVisible(False)
        categories = [f"{row['month_name']} {row['year']}" for row in data]
        sales_series = QLineSeries()
        sales_series.setName('Trading Income')
        sales_series.setPen(QPen(QColor(_chart_colors()['positive']), 3))
        sales_return_series = QLineSeries()
        sales_return_series.setName('Gross Profit')
        sales_return_series.setPen(QPen(QColor(_chart_accent_hex()), 3))
        purchase_series = QLineSeries()
        purchase_series.setName('Direct Expenses')
        purchase_series.setPen(QPen(QColor(_chart_colors()['primary']), 3))
        purchase_return_series = QLineSeries()
        purchase_return_series.setName('Net Profit')
        purchase_return_series.setPen(QPen(QColor(_chart_colors()['warning']), 3))
        for idx, row in enumerate(data):
            sales_series.append(idx, float(row['trading_income']))
            sales_return_series.append(idx, float(row['gross_profit']))
            purchase_series.append(idx, float(row['direct_expenses']))
            purchase_return_series.append(idx, float(row['net_profit']))
        if show_sales_cb.isChecked():
            chart.addSeries(sales_series)
        if show_sales_return_cb.isChecked():
            chart.addSeries(sales_return_series)
        if show_purchase_cb.isChecked():
            chart.addSeries(purchase_series)
        if show_purchase_return_cb.isChecked():
            chart.addSeries(purchase_return_series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setTitleText('Month')
        axis_x.setTitleBrush(QColor(_chart_accent_hex()))
        axis_x.setLabelsColor(QColor(_chart_colors()['axis_label']))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        if show_sales_cb.isChecked():
            sales_series.attachAxis(axis_x)
        if show_sales_return_cb.isChecked():
            sales_return_series.attachAxis(axis_x)
        if show_purchase_cb.isChecked():
            purchase_series.attachAxis(axis_x)
        if show_purchase_return_cb.isChecked():
            purchase_return_series.attachAxis(axis_x)
        axis_y = QValueAxis()
        min_value, max_value = self._chart_axis_range(data, ['trading_income', 'direct_expenses', 'gross_profit', 'net_profit'])
        axis_y.setRange(min_value, max_value)
        axis_y.setTitleText(f'Amount ({CURRENCY_SYMBOL})')
        axis_y.setTitleBrush(QColor(_chart_accent_hex()))
        axis_y.setLabelsColor(QColor(_chart_colors()['axis_label']))
        axis_y.setGridLineColor(QColor(_chart_colors()['grid_line']))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        if show_sales_cb.isChecked():
            sales_series.attachAxis(axis_y)
        if show_sales_return_cb.isChecked():
            sales_return_series.attachAxis(axis_y)
        if show_purchase_cb.isChecked():
            purchase_series.attachAxis(axis_y)
        if show_purchase_return_cb.isChecked():
            purchase_return_series.attachAxis(axis_y)
        chart.setTitle('Monthly Analysis (Line Chart)')
        chart.setTitleBrush(QColor(_chart_accent_hex()))
        chart.legend().setLabelColor(QColor(_chart_colors()['legend_text']))
        chart.legend().setBorderColor(QColor(_chart_colors()['grid_line']))
        return chart

    def _create_sales_vs_purchase_line_chart(self, data: List[Dict[str, Any]], show_sales_cb, show_purchase_cb) -> QChart:
        """Create Sales vs Purchase Line Chart from existing data."""
        if not data:
            return None
        chart = QChart()
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.setBackgroundVisible(False)
        categories = [f"{row['month_name']} {row['year']}" for row in data]
        sales_series = QLineSeries()
        sales_series.setName('Trading Income')
        sales_series.setPen(QPen(QColor(_chart_colors()['positive']), 3))
        purchase_series = QLineSeries()
        purchase_series.setName('Direct Expenses')
        purchase_series.setPen(QPen(QColor(_chart_colors()['primary']), 3))
        for idx, row in enumerate(data):
            sales_series.append(idx, float(row['trading_income']))
            purchase_series.append(idx, float(row['direct_expenses']))
        if show_sales_cb.isChecked():
            chart.addSeries(sales_series)
        if show_purchase_cb.isChecked():
            chart.addSeries(purchase_series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setTitleText('Month')
        axis_x.setTitleBrush(QColor(_chart_accent_hex()))
        axis_x.setLabelsColor(QColor(_chart_colors()['axis_label']))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        if show_sales_cb.isChecked():
            sales_series.attachAxis(axis_x)
        if show_purchase_cb.isChecked():
            purchase_series.attachAxis(axis_x)
        axis_y = QValueAxis()
        min_value, max_value = self._chart_axis_range(data, ['trading_income', 'direct_expenses'])
        axis_y.setRange(min_value, max_value)
        axis_y.setTitleText(f'Amount ({CURRENCY_SYMBOL})')
        axis_y.setTitleBrush(QColor(_chart_accent_hex()))
        axis_y.setLabelsColor(QColor(_chart_colors()['axis_label']))
        axis_y.setGridLineColor(QColor(_chart_colors()['grid_line']))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        if show_sales_cb.isChecked():
            sales_series.attachAxis(axis_y)
        if show_purchase_cb.isChecked():
            purchase_series.attachAxis(axis_y)
        chart.setTitle('Trading Income vs Direct Expenses (Line Chart)')
        chart.setTitleBrush(QColor(_chart_accent_hex()))
        chart.legend().setLabelColor(QColor(_chart_colors()['legend_text']))
        chart.legend().setBorderColor(QColor(_chart_colors()['grid_line']))
        return chart

    def populate_table(self, data: List[Dict[str, Any]], analysis_type: str='All'):
        """Populate table with data."""
        self._prepare_table_for_layout_change()
        if not data:
            self.show_no_data('No data available')
            return
        if analysis_type == 'All':
            columns = ['Month', 'Trading Income', 'Direct Expenses', 'Gross Profit', 'Indirect Income', 'Indirect Expenses', 'Net Profit']
        elif analysis_type in ['Trading Income', 'Sales']:
            columns = ['Month', 'Trading Income']
        elif analysis_type in ['Direct Expenses', 'Purchase']:
            columns = ['Month', 'Direct Expenses']
        elif analysis_type == 'Indirect Income':
            columns = ['Month', 'Indirect Income']
        elif analysis_type == 'Indirect Expenses':
            columns = ['Month', 'Indirect Expenses']
        elif analysis_type == 'Net Profit':
            columns = ['Month', 'Gross Profit', 'Net Profit']
        else:
            columns = ['Month', 'Trading Income', 'Direct Expenses', 'Gross Profit', 'Indirect Income', 'Indirect Expenses', 'Net Profit']

        header = self.table.horizontalHeader()
        header.blockSignals(True)
        self.table.blockSignals(True)
        try:
            self.table.setColumnCount(len(columns))
            self.table.setHorizontalHeaderLabels(columns)
            self.table.setRowCount(len(data))
            for row_idx, row in enumerate(data):
                col_idx = 0
                month_text = f"{row.get('month_name', '')} {row.get('year', '')}".strip()
                self.set_cell(row_idx, col_idx, month_text, align_right=False)
                col_idx += 1
                if analysis_type in ['All', 'Trading Income', 'Sales']:
                    self.set_cell(row_idx, col_idx, self.format_currency(row.get('trading_income', 0)), align_right=True, color=_chart_colors()['positive'])
                    col_idx += 1
                if analysis_type in ['All', 'Direct Expenses', 'Purchase']:
                    self.set_cell(row_idx, col_idx, self.format_currency(row.get('direct_expenses', 0)), align_right=True, color=_chart_colors()['negative'])
                    col_idx += 1
                if analysis_type in ['All', 'Net Profit']:
                    self.set_cell(row_idx, col_idx, self.format_currency(row.get('gross_profit', 0)), align_right=True, color=_chart_accent_hex())
                    col_idx += 1
                if analysis_type in ['All', 'Indirect Income']:
                    self.set_cell(row_idx, col_idx, self.format_currency(row.get('indirect_income', 0)), align_right=True, color=_chart_colors()['positive'])
                    col_idx += 1
                if analysis_type in ['All', 'Indirect Expenses']:
                    self.set_cell(row_idx, col_idx, self.format_currency(row.get('indirect_expenses', 0)), align_right=True, color=_chart_colors()['warning'])
                    col_idx += 1
                if analysis_type in ['All', 'Net Profit']:
                    net_profit = row.get('net_profit', 0)
                    try:
                        net_value = float(net_profit)
                    except (TypeError, ValueError):
                        net_value = 0.0
                    net_color = _chart_colors()['positive'] if net_value >= 0 else _chart_colors()['negative']
                    self.set_cell(row_idx, col_idx, self.format_currency(net_profit), align_right=True, color=net_color)
                    col_idx += 1
        finally:
            self.table.blockSignals(False)
            header.blockSignals(False)
        self.resize_table_columns()

    def set_cell(self, row: int, col: int, text: str, align_right: bool=False, color: str=None):
        """Set table cell."""
        item = QTableWidgetItem(str(text))
        item.setForeground(QColor(color or _chart_colors()['table_text']))
        item.setTextAlignment((Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter)
        self.table.setItem(row, col, item)

    def resize_table_columns(self):
        """Apply stable column sizing without resizeColumnsToContents (Qt crash guard)."""
        if self.table.columnCount() <= 0:
            return
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column_index in range(1, self.table.columnCount()):
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Stretch)

    def format_currency(self, value: Decimal) -> str:
        """Format currency value with the application currency symbol."""
        try:
            return f'{CURRENCY_SYMBOL}{float(value):,.2f}'
        except Exception:
            return f'{CURRENCY_SYMBOL}0.00'

    def show_no_data(self, message: str):
        """Show no data message in table."""
        self._prepare_table_for_layout_change()
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        item = QTableWidgetItem(message)
        item.setForeground(QColor(_chart_accent_hex()))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item)
        self.table.setSpan(0, 0, 1, 1)
        self.current_data = []
        zero = self.format_currency(Decimal('0'))
        self.total_sales_label.setText(f'Trading Income: {zero}')
        self.total_sales_return_label.setText(f'Direct Expenses: {zero}')
        self.net_sales_label.setText(f'Gross Profit: {zero}')
        self.total_purchase_label.setText(f'Indirect Income: {zero}')
        self.total_purchase_return_label.setText(f'Indirect Expenses: {zero}')
        self.net_purchase_label.setText(f'Net Profit: {zero}')
        self.sales_percent_label.setText('Gross Profit %: 0.00%')
        self.sales_return_percent_label.setText('Net Profit %: 0.00%')
        self.purchase_percent_label.setText('Indirect Income %: 0.00%')
        self.purchase_return_percent_label.setText('Indirect Expense %: 0.00%')

    def show_loading(self, message: str):
        """Show a non-blocking loading message in the table."""
        self._prepare_table_for_layout_change()
        self.table.setRowCount(1)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(['Loading'])
        item = QTableWidgetItem(message)
        item.setForeground(QColor(_chart_accent_hex()))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(0, 0, item)