"""Cash Receipt page using shared commercial voucher grid."""
from ui.voucher_grid_common import VoucherGridPage


class CashReceiptPageWidget(VoucherGridPage):
    def __init__(self, db=None, parent=None):
        super().__init__(db=db, voucher_type="cash_receipt", title="Cash Receipt", parent=parent)