"""
Commercial calculation engine for item-based vouchers.

Commercial principle:
    item rows + approved footer adjustments are the source of truth.
    Header totals are fallback only when item rows are unavailable or empty.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def to_amount(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


class CommercialCalculationEngine:
    """Pure calculation helper. It does not write to DB."""

    def first_value(self, data: Dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
        for name in names:
            if name in data and data.get(name) not in (None, ""):
                return data.get(name)
        return default

    def calculate_item_totals(self, items: List[Dict[str, Any]]) -> Dict[str, float]:
        totals = {
            "gross_total": 0.0,
            "discount_total": 0.0,
            "taxable_total": 0.0,
            "cgst_total": 0.0,
            "sgst_total": 0.0,
            "igst_total": 0.0,
            "cess_total": 0.0,
            "tax_total": 0.0,
            "grand_total": 0.0,
        }
        for item in items or []:
            gross = to_amount(self.first_value(item, ["gross_value", "gross", "amount"], 0.0))
            discount = to_amount(self.first_value(item, ["discount", "discount_amount"], 0.0))
            taxable = to_amount(self.first_value(item, ["net_value", "taxable", "taxable_amount"], 0.0))
            cgst = to_amount(self.first_value(item, ["cgst_amount"], 0.0))
            sgst = to_amount(self.first_value(item, ["sgst_amount"], 0.0))
            igst = to_amount(self.first_value(item, ["igst_amount"], 0.0))
            cess = to_amount(self.first_value(item, ["cess_amount"], 0.0))
            tax = to_amount(self.first_value(item, ["tax_amount", "tax_total"], 0.0))
            grand = to_amount(self.first_value(item, ["grand_total", "line_total", "total"], 0.0))

            if taxable == 0.0:
                taxable = max(gross - discount, 0.0)
            split_tax = cgst + sgst + igst + cess
            if tax == 0.0:
                tax = split_tax
            if grand == 0.0:
                grand = taxable + tax

            totals["gross_total"] += gross
            totals["discount_total"] += discount
            totals["taxable_total"] += taxable
            totals["cgst_total"] += cgst
            totals["sgst_total"] += sgst
            totals["igst_total"] += igst
            totals["cess_total"] += cess
            totals["tax_total"] += tax
            totals["grand_total"] += grand
        return {key: round(value, 2) for key, value in totals.items()}

    def calculate_voucher_totals(self, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[Dict[str, float], List[str]]:
        warnings: List[str] = []
        header = header or {}
        items = items or []
        item_totals = self.calculate_item_totals(items)
        has_item_amount = abs(item_totals["grand_total"]) > 0.01 or abs(item_totals["taxable_total"]) > 0.01

        header_grand = to_amount(self.first_value(header, ["grand_total", "net_amount", "total_amount", "amount"], 0.0))
        header_tax = to_amount(self.first_value(header, ["tax_total", "total_tax"], 0.0))
        header_subtotal = to_amount(self.first_value(header, ["sub_total", "subtotal", "taxable_amount"], 0.0))
        header_discount = to_amount(self.first_value(header, ["discount_total", "discount_amount"], 0.0))
        round_off = to_amount(self.first_value(header, ["round_off", "roundoff"], 0.0))
        freight = to_amount(self.first_value(header, ["freight", "freight_amount"], 0.0))

        if has_item_amount:
            totals = dict(item_totals)
            # Header footer adjustments must stay synchronized with commercial validation.
            # IMPORTANT:
            # - Freight increases payable amount.
            # - Discount reduces payable amount.
            # - Round off adjusts final payable amount.
            totals["grand_total"] = round(
                totals["grand_total"] + round_off + freight - header_discount,
                2
            )
            if abs(header_grand) > 0.01 and abs(header_grand - totals["grand_total"]) > 0.05:
                warnings.append(
                    f"Header grand_total {header_grand:.2f} differs from item-based total {totals['grand_total']:.2f}; item-based total used."
                )
        else:
            totals = {
                "gross_total": header_subtotal,
                "discount_total": header_discount,
                "taxable_total": header_subtotal,
                "cgst_total": 0.0,
                "sgst_total": 0.0,
                "igst_total": 0.0,
                "cess_total": 0.0,
                "tax_total": header_tax,
                "grand_total": header_grand,
            }
            warnings.append("Item rows were empty or had zero totals; header totals used as fallback.")

        split_tax = totals["cgst_total"] + totals["sgst_total"] + totals["igst_total"] + totals["cess_total"]
        totals["split_tax_total"] = round(split_tax, 2)
        if totals["tax_total"] == 0.0 and split_tax:
            totals["tax_total"] = round(split_tax, 2)
        return {key: round(value, 2) for key, value in totals.items()}, warnings
