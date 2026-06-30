"""
Shared GST compliance helpers for sales reports and GSTR-1.
"""

import re
from typing import Any, Dict, Optional, Tuple


GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    re.IGNORECASE,
)

GST_STATE_CODES = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman & Diu",
    "26": "Dadra & Nagar Haveli and Daman & Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

STATE_NAME_TO_CODE = {
    re.sub(r"[^a-z0-9]", "", name.lower()): code
    for code, name in GST_STATE_CODES.items()
}
STATE_NAME_TO_CODE.update(
    {
        "jammuandkashmir": "01",
        "orissa": "21",
        "pondicherry": "34",
        "andamanandnicobar": "35",
        "andamanandnicobarislands": "35",
        "dadraandnagarhaveli": "26",
        "damananddiu": "25",
    }
)


def is_valid_gstin(gstin: Any) -> bool:
    """Return True only for structurally valid 15-character GSTIN values."""
    text = str(gstin or "").strip().upper()
    return len(text) == 15 and bool(GSTIN_PATTERN.match(text))


def normalized_gstin(gstin: Any) -> str:
    """Return an uppercase GSTIN when valid, otherwise an empty string."""
    text = str(gstin or "").strip().upper()
    return text if is_valid_gstin(text) else ""


def _clean_state_text(value: Any) -> str:
    """Normalize state text for code lookup."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def state_code(value: Any) -> str:
    """Return a two-digit GST state code from code, POS label, or state name."""
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"^\s*(\d{2})(?:\s*[-:]|\s|$)", text)
    if match and match.group(1) in GST_STATE_CODES:
        return match.group(1)
    if text.isdigit() and len(text) == 2 and text in GST_STATE_CODES:
        return text
    return STATE_NAME_TO_CODE.get(_clean_state_text(text), "")


def place_of_supply_label(value: Any, fallback: Any = "") -> str:
    """Return portal-friendly POS text such as '32-Kerala'."""
    code = state_code(value) or state_code(fallback)
    if code:
        return f"{code}-{GST_STATE_CODES[code]}"
    text = str(value or fallback or "").strip()
    return text


def is_interstate(pos_state: Any, home_state: Any) -> bool:
    """Compare POS and home state by GST state code when possible."""
    pos_code = state_code(pos_state)
    home_code = state_code(home_state)
    if pos_code and home_code:
        return pos_code != home_code
    pos_text = str(pos_state or "").strip()
    home_text = str(home_state or "").strip()
    return bool(pos_text and home_text and pos_text.casefold() != home_text.casefold())


def classify_invoice(gstin: Any, pos_state: Any, home_state: Any, invoice_total: Any) -> str:
    """Classify an invoice as B2B, B2CL, or B2CS using GST rules."""
    if is_valid_gstin(gstin):
        return "B2B"
    try:
        total = float(invoice_total or 0)
    except (TypeError, ValueError):
        total = 0.0
    if is_interstate(pos_state, home_state) and total > 250000:
        return "B2CL"
    return "B2CS"


def tax_totals_for_supply(record: Dict[str, Any], interstate: bool) -> Tuple[float, float, float, float]:
    """Return IGST, CGST, SGST, CESS amounts consistent with supply state."""
    igst = _to_float(record.get("igst_total", record.get("igst", record.get("igst_amount"))))
    cgst = _to_float(record.get("cgst_total", record.get("cgst", record.get("cgst_amount"))))
    sgst = _to_float(record.get("sgst_total", record.get("sgst", record.get("sgst_amount"))))
    cess = _to_float(record.get("cess_total", record.get("cess", record.get("cess_amount"))))
    tax_total = _to_float(record.get("tax_total"))
    if not (igst or cgst or sgst or cess) and tax_total:
        if interstate:
            igst = tax_total
        else:
            cgst = round(tax_total / 2, 2)
            sgst = round(tax_total - cgst, 2)
    if interstate:
        if not igst and (cgst or sgst):
            igst = round(cgst + sgst, 2)
        return igst, 0.0, 0.0, cess
    if not (cgst or sgst) and igst:
        cgst = round(igst / 2, 2)
        sgst = round(igst - cgst, 2)
    return 0.0, cgst, sgst, cess


def gst_slab_rate_from_totals(record: Dict[str, Any]) -> float:
    """Return GST slab percentage using CGST/SGST/IGST only; CESS is excluded."""
    taxable = abs(_to_float(record.get("taxable_value")))
    if taxable <= 0:
        return 0.0
    cgst = abs(_to_float(record.get("cgst")))
    sgst = abs(_to_float(record.get("sgst")))
    igst = abs(_to_float(record.get("igst")))
    gst_tax = cgst + sgst + igst
    if not gst_tax:
        tax_total = abs(_to_float(record.get("tax_total")))
        cess = abs(_to_float(record.get("cess")))
        gst_tax = max(tax_total - cess, 0.0)
    return round(gst_tax / taxable * 100, 2)


def _to_float(value: Optional[Any]) -> float:
    """Convert values used in GST calculations to float."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
