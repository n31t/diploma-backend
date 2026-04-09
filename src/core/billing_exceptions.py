"""
Billing domain errors for programmatic cancel/resume (machine-readable codes).
"""


class BillingServiceError(Exception):
    """Raised when a billing action cannot proceed; maps to HTTP JSON responses."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 400,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)
