"""Structured errors for the password reset HTTP flow."""

RESET_TOKEN_INVALID = "RESET_TOKEN_INVALID"
RESET_TOKEN_EXPIRED = "RESET_TOKEN_EXPIRED"
RESET_TOKEN_USED = "RESET_TOKEN_USED"


class PasswordResetError(Exception):
    """Raised when reset_password cannot complete; maps to JSON body with code."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
