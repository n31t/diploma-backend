# AI Detection via URL — Implementation Reference

Technical documentation for the **current** backend implementation of AI content detection when the input is a public HTTP(S) URL. All behavior statements below are tied to the codebase as of this document; where something is unclear from code alone, it is marked explicitly.

---

## Table of contents

1. [Overview](#overview)
2. [Current end-to-end flow](#current-end-to-end-flow)
3. [Data contracts](#data-contracts)
4. [Article extraction (current behavior)](#article-extraction-current-behavior)
5. [Failure scenarios](#failure-scenarios)
6. [Logging and observability](#logging-and-observability)
7. [Limitations of current implementation](#limitations-of-current-implementation)
8. [Future extension points](#future-extension-points)
9. [Open product questions (optional)](#open-product-questions-optional)
10. [Inventory of involved files and symbols](#inventory-of-involved-files-and-symbols)
11. [Appendix: Documentation vs code discrepancies](#appendix-documentation-vs-code-discrepancies)

---

## Overview

- **Primary HTTP entrypoint:** `POST /api/v1/ai-detection/detect-url`
- **Core pipeline:** verified user → optional Redis rate limit → DB quota check → **single** HTML download with **httpx** → **multi-strategy extraction** in [`NewspaperService`](src/services/newspaper_service.py) (newspaper4k + BeautifulSoup fallbacks; Wikipedia-aware path) → **TextNormalizationService** → ML min length (50 chars) → optional **auto** language resolution (lingua) → **ML microservice** HTTP call → persist history + increment usage → JSON response with limits.
- **Secondary entrypoint:** Telegram bot delegates to the same `URLDetectionService` (no duplicate extraction logic).
- **Important:** The OpenAPI `description` and the handler docstring for `detect_from_url` still mention **Jina Reader** and Markdown stripping. The **actual** implementation uses **httpx + extraction strategies** below. See [Appendix: Documentation vs code discrepancies](#appendix-documentation-vs-code-discrepancies).

**Dependencies (from `pyproject.toml`):** `httpx>=0.28.1`, `newspaper4k>=0.9.3`, `beautifulsoup4`, `lxml` (BS4 parser).

---

## Current end-to-end flow

### HTTP API sequence

1. **Routing:** [`src/main.py`](src/main.py) mounts [`src/api/v1/ai_detection.py`](src/api/v1/ai_detection.py) at prefix `/api/v1`. The router defines `prefix="/ai-detection"`, so the full path is:

```http
POST /api/v1/ai-detection/detect-url
```

2. **Dependencies (run before the handler body):**
   - `Depends(require_verified_user)` — JWT bearer auth; user must exist, be active, and **email verified** ([`src/services/shared/auth_helpers.py`](src/services/shared/auth_helpers.py)).
   - `Depends(check_rate_limit_dependency)` — Redis-backed rate limiter ([`src/api/dependencies/rate_limit.py`](src/api/dependencies/rate_limit.py)); on failure raises **HTTP 429** with `Retry-After` and rate-limit headers. On internal errors in the limiter, the dependency **logs and allows the request** (does not block).

3. **Request validation:** Pydantic model `URLDetectionRequest` — URL scheme/host rules and optional `language` ([`src/api/v1/schemas/ai_detection.py`](src/api/v1/schemas/ai_detection.py)).

4. **Language context:** `context_from_api_language(request.language)` → `DetectionLanguageContext` ([`src/api/v1/schemas/detection_language.py`](src/api/v1/schemas/detection_language.py)). For `auto`, `effective` is initially `"ru"` as a placeholder until text exists.

5. **Service call:** `URLDetectionService.detect_from_url(url, user_id, language=lang_ctx)` ([`src/services/url_detection_service.py`](src/services/url_detection_service.py)).

6. **DB session:** `AIDetectionRepository` uses request-scoped `AsyncSession`; [`src/ioc/database_provider.py`](src/ioc/database_provider.py) **commits** after successful handler completion and **rolls back** on exception.

7. **Response mapping:** Handler builds `AIDetectionWithLimitsResponse` from DTOs and maps enums via `_map_detection_result_to_schema` / `_map_detection_source_to_schema`.

8. **Exception mapping in the route** (same file as handler):

| Exception type | HTTP status | Client `detail` (typical) |
|----------------|-------------|---------------------------|
| `KazakhMlApiUnavailableError` | 503 | ML KK unavailable message |
| `ValueError` with "limit exceeded" (case-insensitive substring) | 429 | Same message |
| Other `ValueError` | 400 | Exception message string |
| `RuntimeError` | 502 | Fixed: `"Failed to fetch or process the requested URL."` |
| Anything else | 500 | Fixed: `"Failed to detect AI content from URL."` |

### Service-layer sequence (`URLDetectionService.detect_from_url`)

Textual sequence (same order as code):

```
can_make_request (DB)
  → if not allowed: ValueError("Request limit exceeded. ...")
  → NewspaperService.fetch_article(url)
  → TextNormalizationService.normalize(article.text, source_format="url")
  → if normalized empty: ValueError("No readable text could be extracted from {url}.")
  → AIDetectionModelService.validate_text(plain_text)  # min 50 chars
  → resolve_effective_language(plain_text, language)     # auto → lingua
  → AIDetectionModelService.detect_ai_text(plain_text, language=effective)
  → AIDetectionRepository.increment_usage(user_id)
  → AIDetectionRepository.create_history_record(..., source="url", file_name=url, ...)
  → return (AIDetectionResultDTO, UserLimitDTO)
```

**Note:** Usage is incremented **after** successful ML inference and **before** history insert. If `create_history_record` failed after `increment_usage`, behavior depends on DB transaction (both are in the same session; a failure would roll back both if raised before commit — not proven by static analysis beyond session scope).

### Dependency injection (Dishka)

[`src/ioc/service_provider.py`](src/ioc/service_provider.py):

| Provider | Scope | Type |
|----------|-------|------|
| `get_newspaper_service` | APP | `NewspaperService` |
| `get_ml_model_service` | APP | `AIDetectionModelService` |
| `get_normalization_service` | APP | `TextNormalizationService` |
| `get_url_detection_service` | REQUEST | `URLDetectionService` (injects newspaper, ML, `AIDetectionRepository`, normalizer) |

The FastAPI router uses `DishkaRoute` and `FromDishka[URLDetectionService]` for the handler.

### Telegram bot sequence (parallel path)

1. User flow in [`src/telegram_bot/routers/analyze.py`](src/telegram_bot/routers/analyze.py): `_run_url_detection` opens a session, resolves linked user, optional rate check, then `ctx.telegram_detection.detect_url(...)`.
2. [`src/services/telegram_detection_service.py`](src/services/telegram_detection_service.py) `TelegramDetectionService.detect_url` calls **`URLDetectionService.detect_from_url`** (same pipeline as HTTP).
3. Exceptions are mapped for user-facing i18n in [`src/telegram_bot/errors.py`](src/telegram_bot/errors.py) (`i18n_key_for_exception`). Raw exception strings are **not** shown to Telegram users.
4. Optional URL validation for bot UX reuses `URLDetectionRequest` via [`src/telegram_bot/urlutil.py`](src/telegram_bot/urlutil.py) (`validate_public_url`).

---

## Data contracts

### HTTP request — `URLDetectionRequest`

Defined in [`src/api/v1/schemas/ai_detection.py`](src/api/v1/schemas/ai_detection.py).

| Field | Type | Notes |
|-------|------|--------|
| `url` | `str` | Required. Validated: `urlparse`, scheme `http` or `https`, non-empty `netloc`. |
| `language` | `DetectionLanguageInput` | Default `"auto"`. Aliases: empty → `auto`; `"kz"` → `"kk"`. |

Validators: `validate_url`, `normalize_url_language_json`.

### HTTP response — `AIDetectionWithLimitsResponse`

Extends `AIDetectionResponse` with `limits: UserLimitsResponse` ([`src/api/v1/schemas/limits.py`](src/api/v1/schemas/limits.py)).

Core fields from [`AIDetectionResponse`](src/api/v1/schemas/ai_detection.py): `result`, `confidence`, `text_preview`, `source`, `file_name`, `metadata`.

For URL detection, the service sets:

- `source` → DTO `DetectionSource.URL` → schema `"url"`.
- `file_name` → the submitted **URL string** (same pattern as using filename for uploads).
- `text_preview` → first **200** characters of analyzed plain text ([`URLDetectionService`](src/services/url_detection_service.py)).
- `metadata` → dict including `url`, `page_title`, `authors`, `publish_date`, lengths, `language_*`, `normalization`, `quality_flags` (from normalization), `processing_time_ms`, plus extraction diagnostics: `extraction_method`, `extraction_fallback_used`, `html_truncated`, `extraction_rejection_notes`.

### Internal DTOs

[`src/dtos/ai_detection_dto.py`](src/dtos/ai_detection_dto.py):

- `NewspaperFetchResultDTO`: `text`, `url`, `title`, `authors`, `publish_date`, `extraction_method` (`newspaper` \| `bs4_wikipedia` \| `bs4_generic`), `fallback_used`, `html_truncated`, `extraction_rejection_notes`.
- `AIDetectionResultDTO`: `result`, `confidence`, `text_preview`, `source`, `file_name`, `metadata`.
- `DetectionSource.URL` — enum value `"url"`.
- `URLDetectionRequestDTO` — **defined** but **not used** in the URL pipeline traced here (possible legacy / unused for this flow).

### Language routing

[`DetectionLanguageContext`](src/api/v1/schemas/detection_language.py): `effective` (`"ru"` \| `"kk"`), `requested` (`"ru"` \| `"kk"` \| `"auto"`).

- `detect_language_from_text`: uses **lingua** on first 2000 characters; Russian vs Kazakh only; non-Kazakh → `"ru"`; on any exception → `"ru"` with warning log.
- `resolve_effective_language`: if `requested != "auto"`, returns context unchanged; else sets `effective` from `detect_language_from_text`.

### ML API payload

[`AIDetectionModelService.detect_ai_text`](src/services/ml_model_service.py) posts JSON:

```json
{"text": "<full analyzed text>", "language": "ru" | "kk"}
```

to `POST /api/v1/detection/` on the base URL selected by language (`ML_API_URL` or `ML_API_URL_KK`).

---

## Article extraction (current behavior)

Orchestration lives in [`src/services/newspaper_service.py`](src/services/newspaper_service.py); BS4 helpers live in [`src/services/url_extraction/`](src/services/url_extraction/).

### Policy: strategy order

| Host | Order |
|------|--------|
| **Wikipedia** (`*.wikipedia.org`, `*.m.wikipedia.org`) | (1) **Wikipedia BeautifulSoup** (`#mw-content-text` / `.mw-parser-output`, strip infobox/navbox/toc/etc.) → (2) **newspaper4k** if wiki text fails quality or throws → (3) **generic BeautifulSoup** |
| **All other hosts** | (1) **newspaper4k** → (2) **generic BeautifulSoup** if newspaper fails quality or throws |

**Single download:** `_download_html` runs once per `fetch_article` call. The same HTML string is passed to every strategy. **No** second HTTP request for fallbacks.

**Thread pool:** newspaper and BS4 work run in `asyncio.run_in_executor` so the event loop is not blocked on large documents.

### URL validation (`_validate_url`)

- `urlparse(url)`; must have scheme `http` or `https` and non-empty `netloc`.
- `ValueError` on invalid input (also validated earlier by Pydantic for API).

### Download (`_download_html`)

- Returns [`DownloadedHtml`](src/services/newspaper_service.py): `content` (possibly truncated), `truncated: bool`, `original_text_length: int` (length of full `response.text` before slice).
- **Cap:** [`MAX_HTML_TEXT_LENGTH`](src/services/url_extraction/constants.py) = **500_000** characters (same as historical behavior).
- **Logging:** `html_downloaded` (always); `html_truncated` (**warning**) when `truncated` is true.
- **Client:** `httpx.AsyncClient(timeout=30, follow_redirects=True, headers=...)`.
- **Errors:** unchanged — `newspaper_http_error` / `newspaper_request_error` → **`RuntimeError`**; empty body → **`ValueError`**.

### Quality gate (extraction acceptance)

[`evaluate_text_quality`](src/services/url_extraction/quality.py) runs on candidate plain text **before** accepting a strategy. Thresholds (stricter than ML’s 50-char minimum) are centralized in [`constants.py`](src/services/url_extraction/constants.py): minimum characters, words, meaningful lines, alphabetic ratio, excessive short-line repetition.

If **all** strategies fail the gate (or throw where applicable), `fetch_article` raises **`RuntimeError`** — maps to **HTTP 502** in the API layer (fixed `detail`).

### Newspaper (`_parse_with_newspaper` — sync, executor)

- `Article.download(input_html=html)` / `parse()`; optional `nlp()` + `summary` when `text` empty.
- On **no text** after summary: raises **`ValueError`** (logged as `newspaper_extraction_failed`; orchestration may continue to BS4).
- On **success:** returns `NewspaperFetchResultDTO` with `extraction_method="newspaper"` (orchestrator may overwrite method on final DTO).

### Generic BeautifulSoup ([`extract_generic_text`](src/services/url_extraction/bs4_generic.py))

- Parser: **`lxml`** via `BeautifulSoup(html, "lxml")`.
- Strips global noisy tags (`script`, `style`, `nav`, …), picks main root (`article`, `main`, `[role='main']`, common `.content` / `#content` selectors, else `body`), removes sidebars/tables/promo blocks inside root, collects text from `p`, `li`, `h2`, `h3`, `blockquote`.
- Title: `h1`, then `og:title`, then `<title>`.

### Wikipedia BeautifulSoup ([`extract_wikipedia_text`](src/services/url_extraction/bs4_wikipedia.py))

- Roots at `#mw-content-text` or `.mw-parser-output`; strips Wikipedia-specific noise (`.infobox`, `.navbox`, `.toc`, `.reflist`, …).
- Title: `#firstHeading` / `.firstHeading`, then fallbacks as above.

### Normalization for `source_format="url"`

[`TextNormalizationService.normalize`](src/services/text_normalization_service.py):

- Full Unicode/whitespace/hyphenation pipeline runs.
- `_remove_boilerplate` **returns immediately** (no boilerplate frequency pass) when `source_format in ("text", "url")` — so URL path **does not** apply frequency-based boilerplate removal used for some other formats.
- `_strip_html_residual` runs only when `source_format == "html"` — **not** for `"url"`, so **no** extra HTML tag stripping pass for URL (newspaper output is expected to be plain text already).

### Minimum text length for detection

- [`AIDetectionModelService.validate_text`](src/services/ml_model_service.py): requires non-empty strip and **`len >= 50`** (logs `text_too_short` if below).
- [`URLDetectionService`](src/services/url_detection_service.py) raises **`ValueError`** with explicit message including `"minimum 50 characters required"` if validation fails.

### Domain-specific / paywall / JS

- **Wikipedia** uses a dedicated BS4 path first (see policy table above).
- **SPAs / heavy JS:** still no headless browser; if static HTML has little text, extraction may still fail after all strategies (**502**).
- **Paywalls:** no cookies/session; same limitations as before.

---

## Failure scenarios

### REST API (`detect_from_url`)

| Situation | Where raised | Logging | Propagation | Client outcome |
|-----------|--------------|---------|-------------|----------------|
| Invalid JWT / unverified email | `require_verified_user` | various `auth_helpers` | `HTTPException` | 401 / 403 |
| Redis rate limit exceeded | `check_rate_limit_dependency` | `rate_limit_exceeded` | `HTTPException` | **429** + headers |
| DB quota exceeded | `AIDetectionRepository.can_make_request` | `url_detection_limit_exceeded` | `ValueError` | **429** (handler checks substring `"limit exceeded"`) |
| Pydantic URL validation | `URLDetectionRequest` | (framework) | validation error | **422** (standard FastAPI) |
| Empty HTTP body | `_download_html` | — | `ValueError` | **400** with message |
| Invalid URL (service `_validate_url`) | `NewspaperService` | — | `ValueError` | **400** |
| HTTP non-success downloading page | `_download_html` | `newspaper_http_error` | `RuntimeError` | **502** (fixed detail) |
| Network error downloading | `_download_html` | `newspaper_request_error` | `RuntimeError` | **502** (fixed detail) |
| Newspaper raises / low-quality text | `_parse_with_newspaper` / orchestrator | `newspaper_extraction_failed` / `newspaper_extraction_rejected` | Next strategy tried; if all fail → **`RuntimeError`** | **502** only if **no** extractor passes quality |
| All extractors fail quality / throw | `NewspaperService.fetch_article` | `extraction_pipeline_failed` | **`RuntimeError`** | **502** (fixed detail) |
| Normalized text empty | `URLDetectionService` | — | `ValueError` | **400** |
| Text shorter than 50 chars after normalization | `URLDetectionService` | `text_too_short` (in `validate_text`) | `ValueError` | **400** |
| Kazakh ML not configured | `AIDetectionModelService._client_for` | — | `KazakhMlApiUnavailableError` (**subclass of `RuntimeError`**) | **503** — **specific handler runs before generic `RuntimeError`** |
| ML API HTTP / connection errors | `detect_ai_text` | `detection_request_failed` / `detection_connection_failed` | **Re-raised** | **500** (generic handler) — **not** mapped to 502 |
| Other ML parsing errors inside `detect_ai_text` | `detect_ai_text` broad `except` | `detection_failed` | Returns **`UNCERTAIN`, 0.0** (no exception) | **200** with low confidence |
| Any other unexpected error | various | `url_detection_unexpected_error` | — | **500** |

**Critical detail:** `KazakhMlApiUnavailableError` inherits `RuntimeError`. The route lists `except KazakhMlApiUnavailableError` **before** `except RuntimeError`, so KK misconfiguration yields **503**, not 502.

### Telegram

| Situation | Handler behavior |
|-----------|-------------------|
| `RateLimitExceeded` | i18n rate limit message |
| `KazakhMlApiUnavailableError` | `error.external.ml_unavailable` |
| `ValueError` | Mapped by substring in [`i18n_key_for_exception`](src/telegram_bot/errors.py); extraction errors that are still `ValueError` may map to `error.user.validation` (not raw text) |
| `RuntimeError` | `error.system.generic` (includes fetch/parse **RuntimeError** from newspaper) |
| Other | Logged `telegram_url_error`; generic system error message |

---

## Logging and observability

### Structured event names (extraction pipeline)

| Event | Typical keys |
|-------|----------------|
| `extraction_pipeline_started` | `url`, `host` |
| `html_downloaded` | `url`, `host`, `html_length`, `html_truncated`, `original_text_length` |
| `html_truncated` | `url`, `host`, `html_length`, `max_length` (warning) |
| `bs4_wikipedia_started` | `url`, `host` |
| `bs4_wikipedia_failed` / `bs4_generic_failed` | `url`, `host`, `error` |
| `bs4_wikipedia_succeeded` / `bs4_generic_succeeded` | `url`, `host`, `text_length` |
| `newspaper_extraction_started` | `url`, `host` |
| `newspaper_extraction_failed` | `url`, `host`, `error`, traceback |
| `newspaper_extraction_succeeded` | `url`, `host`, `text_length` |
| `newspaper_extraction_rejected` | `url`, `host`, `extractor`, `rejection_reason` |
| `extraction_quality_evaluated` | `url`, `host`, `extractor`, metrics, `accepted`, `rejection_reason` |
| `extraction_pipeline_succeeded` | `url`, `host`, `extractor`, `fallback_used`, `text_length`, `word_count`, `paragraph_count`, `html_truncated`, `html_length`, `processing_time_ms` |
| `extraction_pipeline_failed` | `url`, `host`, `html_truncated`, `processing_time_ms`, `notes` |

### Other relevant events

| Event | Module | Typical keys |
|-------|--------|----------------|
| `url_detection_request` / `url_detection_start` / `url_detection_done` / `url_detection_success` | API / URL service | `url`, `user_id`, … |
| `newspaper_http_error` / `newspaper_request_error` | Download | `url`, status or error |
| `newspaper_parsed` | Newspaper | **DEBUG** |
| `text_normalized` | Normalization | `source_format`, counters |
| `analyzing_text` / `detection_complete` | ML service | `text_length`, `ml_language` |
| `usage_incremented` / `detection_history_created` | Repository | usage / history |

### Diagnostic gaps

- **502** responses still use a **fixed** client `detail`; see `metadata.extraction_rejection_notes` / server logs for strategy-level detail.
- Very large HTML truncation can still hurt parsers even when logged (`html_truncated`).

---

## Limitations of current implementation

1. **No headless browser:** JS-rendered sites may still yield little or no text in static HTML.
2. **Truncation:** HTML is capped at **500 KB** characters; long pages may be partially parsed — `html_truncated` in metadata/logs flags this.
3. **Heuristic BS4:** Generic/Wikipedia selectors cannot match every site layout; worst case ends in **502** after failed quality gates.
4. **No paywall / auth handling:** No cookies or session for paid content.
5. **Normalization:** `source_format="url"` still skips frequency boilerplate and HTML residual passes — see [Article extraction](#article-extraction-current-behavior).
6. **ML errors:** Connection/HTTP failures from ML typically yield **500** on REST (except Kazakh config → 503).
7. **OpenAPI drift:** Jina Reader / Markdown still documented in OpenAPI — **not** implemented.
8. **Unused DTO:** `URLDetectionRequestDTO` is not wired into this flow in the traced code paths.

---

## Future extension points

| Location | Notes |
|----------|--------|
| [`src/services/url_extraction/bs4_generic.py`](src/services/url_extraction/bs4_generic.py) | Add selectors, language-specific noise lists, or readability-style scoring. |
| [`src/services/url_extraction/bs4_wikipedia.py`](src/services/url_extraction/bs4_wikipedia.py) | Tune MediaWiki class names / sister projects (Wiktionary, etc.). |
| [`src/services/url_extraction/quality.py`](src/services/url_extraction/quality.py) | Adjust thresholds or add domain-aware rules. |
| [`NewspaperService.fetch_article`](src/services/newspaper_service.py) | Insert additional strategies in the orchestration chain (still one download). |
| [`TextNormalizationService.normalize`](src/services/text_normalization_service.py) | Optional new `source_format` if extractors emit HTML-heavy strings. |

---

## Open product questions (optional)

1. Should extraction **502** responses expose structured error codes to clients?
2. Should **truncation** raise a distinct user-visible warning?
3. Is **headless rendering** ever in scope for SPAs?

---

## Inventory of involved files and symbols

### API layer

| File | Responsibility |
|------|----------------|
| [`src/main.py`](src/main.py) | Mounts `/api/v1` + `ai_detection` router |
| [`src/api/v1/ai_detection.py`](src/api/v1/ai_detection.py) | `detect_from_url`, `AIDetectionWithLimitsResponse`, exception mapping, mappers |
| [`src/api/v1/schemas/ai_detection.py`](src/api/v1/schemas/ai_detection.py) | `URLDetectionRequest`, `AIDetectionResponse`, enums |
| [`src/api/v1/schemas/detection_language.py`](src/api/v1/schemas/detection_language.py) | `DetectionLanguageContext`, `context_from_api_language`, `resolve_effective_language`, lingua detector |
| [`src/api/v1/schemas/limits.py`](src/api/v1/schemas/limits.py) | `UserLimitsResponse` |
| [`src/api/dependencies/rate_limit.py`](src/api/dependencies/rate_limit.py) | `check_rate_limit_dependency` |

### Services

| File | Classes / functions |
|------|---------------------|
| [`src/services/url_detection_service.py`](src/services/url_detection_service.py) | `URLDetectionService.detect_from_url` |
| [`src/services/newspaper_service.py`](src/services/newspaper_service.py) | `NewspaperService`, `fetch_article`, `DownloadedHtml`, `_download_html`, `_parse_with_newspaper`, `_validate_url` |
| [`src/services/url_extraction/constants.py`](src/services/url_extraction/constants.py) | `MAX_HTML_TEXT_LENGTH`, selectors, thresholds |
| [`src/services/url_extraction/domain.py`](src/services/url_extraction/domain.py) | `is_wikipedia_host`, `parsed_host` |
| [`src/services/url_extraction/quality.py`](src/services/url_extraction/quality.py) | `evaluate_text_quality`, `ExtractionQualityResult` |
| [`src/services/url_extraction/bs4_generic.py`](src/services/url_extraction/bs4_generic.py) | `extract_generic_text` |
| [`src/services/url_extraction/bs4_wikipedia.py`](src/services/url_extraction/bs4_wikipedia.py) | `extract_wikipedia_text` |
| [`src/services/text_normalization_service.py`](src/services/text_normalization_service.py) | `TextNormalizationService.normalize` |
| [`src/services/ml_model_service.py`](src/services/ml_model_service.py) | `AIDetectionModelService`, `KazakhMlApiUnavailableError`, `validate_text`, `detect_ai_text` |
| [`src/services/telegram_detection_service.py`](src/services/telegram_detection_service.py) | `TelegramDetectionService.detect_url`, `TelegramDetectionResult`, `_build_result` |

### Persistence & DI

| File | Responsibility |
|------|----------------|
| [`src/repositories/ai_detection_repository.py`](src/repositories/ai_detection_repository.py) | `can_make_request`, `increment_usage`, `create_history_record` |
| [`src/ioc/service_provider.py`](src/ioc/service_provider.py) | Wires `URLDetectionService` and `NewspaperService` |
| [`src/ioc/database_provider.py`](src/ioc/database_provider.py) | Per-request session commit/rollback |

### DTOs & config

| File | Notes |
|------|--------|
| [`src/dtos/ai_detection_dto.py`](src/dtos/ai_detection_dto.py) | `NewspaperFetchResultDTO`, `AIDetectionResultDTO`, `DetectionSource` |
| [`src/dtos/limits_dto.py`](src/dtos/limits_dto.py) | `UserLimitDTO` (used in responses) |
| [`src/core/billing.py`](src/core/billing.py) | `FREE_DAILY_LIMIT`, `FREE_MONTHLY_LIMIT` (defaults for new users) |

### Auth

| File | Responsibility |
|------|----------------|
| [`src/services/shared/auth_helpers.py`](src/services/shared/auth_helpers.py) | `require_verified_user` |

### Tests

| File | Responsibility |
|------|----------------|
| [`tests/test_url_article_extraction.py`](tests/test_url_article_extraction.py) | Quality gates, BS4 extractors, `NewspaperService` orchestration (mocked download / newspaper) |

### Telegram (URL path only)

| File | Responsibility |
|------|----------------|
| [`src/telegram_bot/routers/analyze.py`](src/telegram_bot/routers/analyze.py) | `_run_url_detection` |
| [`src/telegram_bot/errors.py`](src/telegram_bot/errors.py) | `i18n_key_for_exception` |
| [`src/telegram_bot/urlutil.py`](src/telegram_bot/urlutil.py) | `validate_public_url` (optional validation) |

### Environment variables affecting this flow

| Variable | Role |
|----------|------|
| `ML_API_URL` | Base URL for Russian ML backend (default `http://ml-api:8000`) |
| `ML_API_URL_KK` | Kazakh ML backend; if unset, `kk` routing raises `KazakhMlApiUnavailableError` |

**Not found:** No env vars for user-agent, HTTP timeout, or HTML cap (see [`constants.py`](src/services/url_extraction/constants.py) `MAX_HTML_TEXT_LENGTH` and [`newspaper_service.py`](src/services/newspaper_service.py) `REQUEST_TIMEOUT`).

---

## Appendix: Documentation vs code discrepancies

| Documented in OpenAPI / docstring | Actual code |
|---------------------------------|-------------|
| “Fetches … via **Jina Reader** (r.jina.ai)” | **httpx** GET + **multi-strategy** extraction (newspaper4k + BeautifulSoup fallbacks) |
| “Strip Markdown → plain text” | **No** Markdown step |
| “502 — Jina Reader is unreachable” | **502** for **`RuntimeError`** from download failure or when **all** extraction strategies fail (`extraction_pipeline_failed`) |
| Docstring: response `source = "file"` | **`source` is `"url"`** (`DetectionSource.URL`) |
| `detect-text` doc mentions 100/1000 free tier | [`src/core/billing.py`](src/core/billing.py) defaults are **10** daily / **100** monthly for new `UserLimit` rows — **verify** premium vs free in billing/subscription code if product accuracy matters |

---

## Document history

- Written to reflect the implementation in repository paths referenced above; behavior should be re-verified after any refactor of URL detection.
