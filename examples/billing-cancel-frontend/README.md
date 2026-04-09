# Billing cancel / resume — пример для фронтенда

Репозиторий `diploma-backend` не содержит приложения UI. Файл [`BillingPage.example.tsx`](BillingPage.example.tsx) — эталонная реализация экрана биллинга под API:

- `GET /api/v1/billing/subscription`
- `POST /api/v1/billing/cancel`
- `POST /api/v1/billing/resume`
- `POST /api/v1/billing/portal`

Скопируйте компонент в свой Next.js/React проект, задайте `NEXT_PUBLIC_API_URL` и способ хранения access token (пример использует `localStorage`).

Ошибки API: JSON `{ "detail": string, "code": string }` — см. [документацию](../docs/STRIPE_PREMIUM_FEATURES.md).
