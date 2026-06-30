from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "ui" / "monthly_analysis_page.py"
t = p.read_text(encoding="utf-8")

replacements = [
    (
        'item.setStyleSheet("color: #f3f4f6; font-weight: bold; padding: 6px 12px; background: #1e293b; border-radius: 6px;")',
        'item.setStyleSheet(_metric_chip_style(_report_theme_colors()["input_text"]))',
    ),
    (
        'item.setStyleSheet("color: #fbbf24; font-weight: bold; padding: 6px 12px; background: #1e293b; border-radius: 6px;")',
        'item.setStyleSheet(_metric_chip_style(_chart_accent_hex()))',
    ),
    (
        'self.total_sales_label.setStyleSheet("color: #059669; font-weight: bold; padding: 6px 12px; background: #1e293b; border-radius: 6px;")',
        'self.total_sales_label.setStyleSheet(_metric_chip_style("#059669"))',
    ),
    (
        'self.net_sales_label.setStyleSheet("color: #059669; font-weight: bold; padding: 6px 12px; background: #1e293b; border-radius: 6px;")',
        'self.net_sales_label.setStyleSheet(_metric_chip_style("#059669"))',
    ),
    (
        'self.total_sales_return_label.setStyleSheet("color: #dc2626; font-weight: bold; padding: 6px 12px; background: #1e293b; border-radius: 6px;")',
        'self.total_sales_return_label.setStyleSheet(_metric_chip_style("#dc2626"))',
    ),
    (
        'self.total_purchase_return_label.setStyleSheet("color: #dc2626; font-weight: bold; padding: 6px 12px; background: #1e293b; border-radius: 6px;")',
        'self.total_purchase_return_label.setStyleSheet(_metric_chip_style("#dc2626"))',
    ),
    (
        'chart_window.setStyleSheet("background-color: #111827;")',
        "chart_window.setStyleSheet(page_background_style())",
    ),
    (
        'chart_view.setStyleSheet("background-color: #111827; border: 1px solid #374151; border-radius: 4px;")',
        'chart_view.setStyleSheet(report_filter_frame_style("QChartView"))',
    ),
    (
        'chart_type_label.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")',
        "chart_type_label.setStyleSheet(compact_label_style())",
    ),
    (
        'viz_type_label.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")',
        "viz_type_label.setStyleSheet(compact_label_style())",
    ),
    ('QColor("#fbbf24")', 'QColor(_chart_accent_hex())'),
    ('color="#fbbf24"', "color=_chart_accent_hex()"),
]
for old, new in replacements:
    t = t.replace(old, new)

# Combo boxes in chart dialog still use inline dark styles
t = t.replace(
    """                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 3px;
                color: #f1f5f9;""",
    """                background-color: transparent;
                border: none;
                color: inherit;""",
)

p.write_text(t, encoding="utf-8")
print("patched monthly_analysis_page.py")
