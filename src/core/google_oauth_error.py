"""Structured errors for Google OAuth login (JSON body with code)."""


class GoogleOAuthError(Exception):
    __slots__ = ("code", "message", "http_status")

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


GOOGLE_OAUTH_DISABLED = "GOOGLE_OAUTH_DISABLED"
GOOGLE_OAUTH_NOT_CONFIGURED = "GOOGLE_OAUTH_NOT_CONFIGURED"
INVALID_REDIRECT_URI = "INVALID_REDIRECT_URI"
INVALID_GOOGLE_CODE = "INVALID_GOOGLE_CODE"
GOOGLE_EMAIL_NOT_VERIFIED = "GOOGLE_EMAIL_NOT_VERIFIED"
OAUTH_ACCOUNT_CONFLICT = "OAUTH_ACCOUNT_CONFLICT"
ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
