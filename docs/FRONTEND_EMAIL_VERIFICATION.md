# Email verification — фронтенд и контракт API

Реализация UI: репозиторий **diploma-front** (Next.js).

## API (бэкенд)

| Действие | Метод | URL | Тело / заголовки |
|----------|--------|-----|------------------|
| Регистрация | `POST` | `/api/v1/auth/register` | токены в ответе |
| Текущий пользователь | `GET` | `/api/v1/auth/me` | `Authorization: Bearer` |
| Подтвердить email | `POST` | `/api/v1/auth/verify-email` | `{"token": "<из URL>"}` |
| Отправить ссылку снова | `POST` | `/api/v1/auth/resend-verification` | Bearer |

`GET /me` включает `is_verified`. Пока `false`, «ядро» API отвечает **403** `Email address not verified`.

Ссылка в письме: `{FRONTEND_URL}/verify-email?token=...` — `FRONTEND_URL` на бэкенде должен совпадать с публичным origin фронта.

## Реализовано в diploma-front

- `framer-motion` — анимации на `/verify-email` и баннере.
- `/verify-email` — query `token`, вызов API, состояния loading / success / error.
- `/check-email` — после регистрации; повторная отправка письма.
- Баннер в `app/dashboard/layout.tsx` для `!is_verified`.
- `lib/api.ts` — `verifyEmail`, `resendVerification`; тип `User.is_verified`.

## Переменные

- **Фронт:** `NEXT_PUBLIC_API_BASE_URL` (полный URL API) или прокси `/api/v1` через `next.config.mjs`.
- **Бэкенд:** `FRONTEND_URL`, переменные `SMTP_*` для продакшена (см. [AUTHENTICATION.md](AUTHENTICATION.md)).
