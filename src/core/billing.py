"""
Billing tier constants.

Single source of truth for free / premium request limits.
"""

FREE_DAILY_LIMIT = 10
FREE_MONTHLY_LIMIT = 100

PREMIUM_DAILY_LIMIT = 100
PREMIUM_MONTHLY_LIMIT = 1000

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
