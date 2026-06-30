"""Cash Payment logic wrapper."""
from bizora_core.cash_bank_voucher_logic import CashBankVoucherLogic


class CashPaymentLogic(CashBankVoucherLogic):
    def __init__(self, db):
        super().__init__(db, "cash_payment")
