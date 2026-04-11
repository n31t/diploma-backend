"""DNS-based deliverability checks for email addresses (registration)."""

from email_validator import EmailNotValidError, validate_email


def validate_deliverable_email(address: str, timeout: int) -> str:
    """
    Validate syntax and that the domain can receive email (DNS MX / deliverability).

    Raises ValueError with a message suitable for API responses if validation fails.
    """
    try:
        info = validate_email(
            address,
            check_deliverability=True,
            timeout=timeout,
        )
        return info.normalized
    except EmailNotValidError as e:
        raise ValueError(str(e)) from e
