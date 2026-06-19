# Telegram Mini Shop

Production-oriented Telegram Mini App storefront built with Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Jinja2, and vanilla JavaScript.

The app still opens inside Telegram and uses the Telegram WebView SDK for `ready()` and `expand()`, but it does not depend on Telegram auth, `initData`, or Telegram user records.

## Features

- Catalog, product detail, cart, and checkout.
- Anonymous checkout with required Telegram username.
- Server-side order creation, inventory checks, and admin management.
- Telegram Bot API order notifications only.
- Admin login with username/password and signed cookie.

## Checkout

The checkout form requires:

- `Telegram Username`

It accepts values like `@username` or `username`, normalizes them to `@username`, stores them on the order, and includes them in admin views and Telegram notifications.

## Local Run

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost/`.

Admin panel: `http://localhost/admin/login`.

## Environment

```env
DATABASE_URL=postgresql+psycopg://tgshop:change-me@db:5432/tgshop
TELEGRAM_BOT_TOKEN=123456:bot-token
ADMIN_CHAT_ID=123456789
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use-a-long-random-password
APP_SECRET_KEY=use-openssl-rand-base64-48-or-longer
PUBLIC_BASE_URL=https://your-domain.example
```

`TELEGRAM_BOT_TOKEN` is used only for order notifications.

## Migration

Run Alembic after deploying:

```bash
docker compose exec web alembic upgrade head
```

## Verification

- Mini App opens without Telegram auth.
- No Telegram session is created.
- No Telegram user record is required.
- Catalog, cart, and checkout work anonymously.
- Telegram username is required and saved.
- Admin orders and Telegram notifications include the username.
