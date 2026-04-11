"""Format Telegram messages (HTML) for limits, stats, history, detection results."""

from __future__ import annotations

import html
from datetime import datetime
from typing import TYPE_CHECKING

from src.core.billing import (
    FREE_DAILY_LIMIT,
    FREE_MONTHLY_LIMIT,
    PREMIUM_DAILY_LIMIT,
    PREMIUM_MONTHLY_LIMIT,
)
from src.dtos.limits_dto import UserLimitDTO

if TYPE_CHECKING:
    from src.services.telegram_detection_service import TelegramDetectionResult

from src.telegram_bot.i18n import result_label, t, verdict_sentence


def _confidence_bar(confidence: float, width: int = 10) -> str:
    filled = round(confidence * width)
    return "█" * filled + "░" * (width - filled)


def _dt_utc(x: datetime) -> str:
    return x.strftime("%Y-%m-%d %H:%M UTC")


def _plan_display_name(dto: UserLimitDTO, locale: str) -> str:
    if dto.is_premium:
        return t("usage.plan_name_premium", locale)
    return t("usage.plan_name_free", locale)


def format_detection_result(r: "TelegramDetectionResult", locale: str) -> str:
    """HTML-formatted detection reply."""
    emoji = {
        "ai_generated": "🤖",
        "human_written": "✍️",
        "uncertain": "🤔",
    }.get(r.result.value, "❓")
    short_label = result_label(r.result.value, locale)
    verdict_long = verdict_sentence(r.result.value, locale)
    bar = _confidence_bar(r.confidence)
    pct = round(r.confidence * 100)

    kind_key = {
        "text": "result.kind_text",
        "file": "result.kind_file",
        "image": "result.kind_image",
        "url": "result.kind_url",
    }.get(r.detection_kind, "result.kind_text")

    lines = [
        t("result.verdict_line", locale, emoji=emoji, verdict=html.escape(verdict_long)),
        t("result.confidence_plain", locale, pct=pct),
        f"{html.escape(bar)}",
        t(kind_key, locale),
        t(
            "result.ml_lang",
            locale,
            req=html.escape(str(r.language_requested)),
            eff=html.escape(str(r.language_effective)),
        ),
    ]
    if r.file_name:
        safe_name = html.escape(r.file_name)
        lines.append(f"{t('result.file_label', locale)}: <code>{safe_name}</code>")
    lines.append(
        t(
            "result.meta_time_words",
            locale,
            ms=r.processing_time_ms,
            words=r.word_count,
        )
    )
    lines.append(
        t(
            "result.remaining",
            locale,
            d=r.daily_remaining,
            m=r.monthly_remaining,
        )
    )
    return "\n".join(lines)


def format_usage_card(dto: UserLimitDTO, locale: str) -> str:
    """Localized usage card (HTML)."""
    plan_name = _plan_display_name(dto, locale)
    title = html.escape(t("usage.card_title", locale, plan_name=plan_name))
    lines = [
        f"<b>{title}</b>",
        t(
            "usage.today",
            locale,
            used=dto.daily_used,
            limit=dto.daily_limit,
            remaining=dto.daily_remaining,
        ),
        t("usage.daily_reset", locale, when=_dt_utc(dto.daily_reset_at)),
        t(
            "usage.month",
            locale,
            used=dto.monthly_used,
            limit=dto.monthly_limit,
            remaining=dto.monthly_remaining,
        ),
        t("usage.monthly_reset", locale, when=_dt_utc(dto.monthly_reset_at)),
        t("usage.total_checks", locale, n=dto.total_requests),
        t(
            "usage.can_request_yes" if dto.can_make_request else "usage.can_request_no",
            locale,
        ),
    ]
    return "\n".join(lines)


def format_limits(dto: UserLimitDTO, locale: str) -> str:
    """Alias for usage card (backwards compatibility)."""
    return format_usage_card(dto, locale)


def format_stats(stats: dict, locale: str) -> str:
    total = stats.get("total_detections") or 0
    if total == 0:
        return (
            f"<b>{html.escape(t('stats.empty_title', locale))}</b>\n"
            f"{html.escape(t('stats.empty_body', locale))}"
        )

    br = stats.get("results_breakdown") or {}
    ai_n = int(br.get("ai_generated", 0))
    hu_n = int(br.get("human_written", 0))
    un_n = int(br.get("uncertain", 0))
    ai_pct = round(100.0 * ai_n / total, 1)
    hu_pct = round(100.0 * hu_n / total, 1)
    un_pct = round(100.0 * un_n / total, 1)
    avg = stats.get("average_confidence") or 0.0
    avg_pct = round(float(avg) * 100, 1)

    title = html.escape(t("stats.title", locale))
    parts = [
        f"<b>{title}</b>",
        t("stats.total", locale, n=total),
        t("stats.avg_conf", locale, pct=avg_pct),
        t("stats.breakdown_ai", locale, n=ai_n, pct=ai_pct),
        t("stats.breakdown_human", locale, n=hu_n, pct=hu_pct),
        t("stats.breakdown_uncertain", locale, n=un_n, pct=un_pct),
    ]
    return "\n".join(parts)


def format_history_page(
    records: list,
    locale: str,
    offset: int,
) -> str:
    if not records:
        return (
            f"<b>{html.escape(t('history.empty_title', locale))}</b>\n"
            f"{html.escape(t('history.empty_body', locale))}"
        )

    emoji_map = {
        "ai_generated": "🤖",
        "human_written": "✍️",
        "uncertain": "🤔",
    }
    title = html.escape(t("history.title", locale))
    lines = [f"<b>{title}</b>"]
    for i, rec in enumerate(records, start=offset + 1):
        preview = (rec.text_preview or "")[:80]
        if len(rec.text_preview or "") > 80:
            preview += "…"
        em = emoji_map.get(rec.result, "❓")
        lbl = result_label(rec.result, locale)
        card = t(
            "history.card",
            locale,
            i=i,
            emoji=em,
            label=html.escape(lbl),
            pct=round(rec.confidence * 100),
            preview=html.escape(preview),
        )
        lines.append(card)
    return "\n".join(lines)


def format_premium_screen(
    locale: str,
    limits: UserLimitDTO,
) -> str:
    """HTML body for Premium screen: factual limits + comparison from billing constants."""
    headline = t(
        "premium.headline",
        locale,
        plan=html.escape(limits.plan_type),
    )
    current = t(
        "premium.current_limits",
        locale,
        daily_used=limits.daily_used,
        daily_limit=limits.daily_limit,
        monthly_used=limits.monthly_used,
        monthly_limit=limits.monthly_limit,
    )
    status = t(
        "premium.premium_yes" if limits.is_premium else "premium.premium_no",
        locale,
    )
    compare = t(
        "premium.compare_row",
        locale,
        fd=FREE_DAILY_LIMIT,
        fm=FREE_MONTHLY_LIMIT,
        pd=PREMIUM_DAILY_LIMIT,
        pm=PREMIUM_MONTHLY_LIMIT,
    )
    parts = [
        f"<b>{html.escape(t('premium.title', locale))}</b>",
        headline,
        status,
        current,
        f"<b>{html.escape(t('premium.compare_title', locale))}</b>",
        t("premium.benefit_intro", locale),
        compare,
    ]
    return "\n".join(parts)
