"""Bank Payment page using shared commercial voucher grid."""
from ui.voucher_grid_common import VoucherGridPage


class BankPaymentPageWidget(VoucherGridPage):
    def __init__(self, db=None, parent=None):
        super().__init__(db=db, voucher_type="bank_payment", title="Bank Payment", parent=parent)