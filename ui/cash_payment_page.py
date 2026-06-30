"""Cash Payment page using shared commercial voucher grid."""
from ui.voucher_grid_common import VoucherGridPage


class CashPaymentPageWidget(VoucherGridPage):
    def __init__(self, db=None, parent=None):
        super().__init__(db=db, voucher_type="cash_payment", title="Cash Payment", parent=parent)