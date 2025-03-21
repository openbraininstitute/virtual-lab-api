from enum import StrEnum
from http import HTTPStatus


# TODO: NOTE: do we keep the suffix ERROR or not ?
class AccountingErrorValue(StrEnum):
    CREATE_VIRTUAL_LAB_ACCOUNT_ERROR = "ACCOUNTING_CREATE_VIRTUAL_LAB_ACCOUNT_ERROR"
    CREATE_PROJECT_ACCOUNT_ERROR = "ACCOUNTING_CREATE_PROJECT_ACCOUNT_ERROR"

    FETCH_VIRTUAL_LAB_BALANCE_ERROR = "ACCOUNTING_FETCH_VIRTUAL_LAB_BALANCE_ERROR"
    FETCH_PROJECT_BALANCE_ERROR = "ACCOUNTING_FETCH_PROJECT_BALANCE_ERROR"

    TOP_UP_VIRTUAL_LAB_ACCOUNT_ERROR = "ACCOUNTING_TOP_UP_VIRTUAL_LAB_ACCOUNT_ERROR"
    ASSIGN_PROJECT_BUDGET_ERROR = "ACCOUNTING_ASSIGN_PROJECT_BUDGET_ERROR"
    REVERSE_PROJECT_BUDGET_ERROR = "ACCOUNTING_REVERSE_PROJECT_BUDGET_ERROR"
    MOVE_PROJECT_BUDGET_ERROR = "ACCOUNTING_MOVE_PROJECT_BUDGET_ERROR"

    FETCH_VIRTUAL_LAB_REPORTS_ERROR = "ACCOUNTING_FETCH_VIRTUAL_LAB_REPORTS_ERROR"
    FETCH_PROJECT_REPORTS_ERROR = "ACCOUNTING_FETCH_PROJECT_REPORTS_ERROR"

    CREATE_VIRTUAL_LAB_DISCOUNT_ERROR = "ACCOUNTING_CREATE_VIRTUAL_LAB_DISCOUNT_ERROR"

    GENERIC_ERROR = "ACCOUNTING_GENERIC_ERROR"


class AccountingError(Exception):
    message: str | None
    type: AccountingErrorValue | None
    http_status_code: HTTPStatus | None

    def __init__(
        self,
        *,
        message: str | None = None,
        type: AccountingErrorValue | None = None,
        http_status_code: HTTPStatus | None = None,
    ) -> None:
        self.message = message
        self.type = type
        self.http_status_code = http_status_code
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message}"
