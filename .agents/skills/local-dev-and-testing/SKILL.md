---
name: local-dev-and-testing
description: How to run the tg-mini-shop Next.js app locally (Postgres in Docker, Prisma migrate + seed), what credentials to use, how to test the storefront end-to-end without a real Telegram client, how to test it inside Telegram with ngrok, and where the route-group layout split lives. Read this before touching the repo.
---

# Local dev and testing — tg-mini-shop

## Stack

Next.js 14 (App Router) + TailwindCSS + Prisma 6 + PostgreSQL. Telegram WebApp SDK on the storefront, Telegram Bot API for order notifications. Admin panel at `/admin` protected by an `ADMIN_PASSWORD` + signed JWT cookie (`jose`, HS256).

## One-time local setup (verified)

Skip individual steps if your environment.yaml already runs them.

```bash
# 1. Postgres in Docker (avoids apt issues, fully isolated)
docker run -d --name tg-mini-pg \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=tgshop \
  -p 5432:5432 postgres:16-alpine

# 2. .env for browser-based dev (no real Telegram client needed)
cat > .env <<'EOF'
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/tgshop?schema=public"
TELEGRAM_BOT_TOKEN=""
ADMIN_CHAT_ID=""
ADMIN_PASSWORD="admin"
ADMIN_SESSION_SECRET="dev-secret-please-change-me-to-a-long-random-value-1234567890"
SKIP_TELEGRAM_VALIDATION="1"
EOF

# 3. Install + migrate + seed
npm install
npx prisma generate
npx prisma migrate dev --name init   # first-time. Use `migrate deploy` after.
npm run db:seed                       # 4 categories + 6 products

# 4. Run
npm run dev    # http://localhost:3000
```

If the container already exists from a previous session: `docker start tg-mini-pg` is enough. If the schema is out of date: `npx prisma migrate deploy`. If the DB is empty: `npm run db:seed`.

## Test credentials (local only — never used in production)

- **Admin login:** password `admin` (from `ADMIN_PASSWORD` in `.env`).
- **Synthetic Telegram user** (when `SKIP_TELEGRAM_VALIDATION=1`): id `1000000`, username `dev`. Created on demand by `getTelegramUserFromHeaders()` so the storefront works in a normal browser tab without `window.Telegram.WebApp`.

`ADMIN_SESSION_SECRET` must be a long random string in production — `openssl rand -base64 48` is fine. The dev value above is intentionally placeholder.

## Three ways to test the storefront

### 1. Browser-only (fastest, what local dev uses)

Set `SKIP_TELEGRAM_VALIDATION=1` and leave `TELEGRAM_BOT_TOKEN` / `ADMIN_CHAT_ID` empty:

- `initData` HMAC check is bypassed; a synthetic dev user is injected.
- `/api/order` writes to the DB normally; bot DMs are no-ops because the token is empty.
- Everything except real bot notifications is testable end-to-end (storefront, cart, checkout, admin, order status).

### 2. Inside Telegram via ngrok (real Mini App, real bot DMs)

For verifying real `initData` HMAC validation and admin/user DMs.

```bash
# Terminal 1: dev server
npm run dev

# Terminal 2: tunnel localhost:3000 to a public HTTPS URL
ngrok http 3000
# copy the https://<random>.ngrok-free.app URL it prints
```

Then in `.env` set the **real** values and **remove** `SKIP_TELEGRAM_VALIDATION`:

```env
TELEGRAM_BOT_TOKEN="<from @BotFather>"
ADMIN_CHAT_ID="<your Telegram numeric id, get it from @userinfobot>"
# remove or set SKIP_TELEGRAM_VALIDATION=""
```

In Telegram talk to `@BotFather`:

- `/newapp` (or `/setmenubutton`) → choose your bot → set the Mini App URL to your ngrok URL.
- `/setdomain` → your bot → enter the ngrok hostname (without scheme).

In Telegram, send `/start` to your bot from the admin account first — Telegram rejects bot DMs to users who haven't initiated a chat. Then open the Mini App from the bot menu button or the inline keyboard.

### 3. Production via Vercel + a managed Postgres

See README. Use `npx prisma migrate deploy` (not `migrate dev`) against the production DB. Image uploads need a real object store (Vercel Blob / S3 / R2) — `/public/uploads` is read-only on Vercel. The admin form already accepts a direct image URL as a fallback.

## Key URLs and routing

- **Storefront:** `/`, `/category/[id]`, `/product/[id]`, `/cart`, `/checkout`, `/orders/success`, `/profile`. All wrapped by `src/app/(shop)/layout.tsx` which provides the mobile frame `mx-auto max-w-md pb-24`.
- **Admin login:** `/admin/login`. Lives outside the panel layout so it renders as a centered card with no sidebar.
- **Admin (auth-required):** `/admin`, `/admin/categories`, `/admin/products`, `/admin/orders`. Live in `src/app/admin/(panel)/...` which provides the sidebar layout. `src/middleware.ts` protects `/admin/*` and redirects unauthenticated requests to `/admin/login?next=...`.
- **API:** `/api/products`, `/api/categories`, `/api/cart`, `/api/order`, `/api/orders`, `/api/favorites` and the admin namespace `/api/admin/{login,logout,categories,products,orders,upload}` plus `[id]` variants.

## Route-group layout split (don't undo this)

The root layout (`src/app/layout.tsx`) is intentionally minimal — `<Providers>{children}</Providers>` and the Telegram WebApp script. The mobile frame wraps **only** the storefront via `src/app/(shop)/layout.tsx`. The admin sidebar wraps **only** the protected admin pages via `src/app/admin/(panel)/layout.tsx`. `/admin/login` deliberately sits outside both.

If you reintroduce a global `max-w-md` wrapper in the root layout, the admin panel will be squished into a 448px column and `/admin/login` will inherit the sidebar.

## Useful commands

```bash
npm run lint            # next lint
npx tsc --noEmit        # typecheck (run `rm -rf .next` first if you've moved files)
npm run build           # full production build
npm run db:seed         # re-seed demo categories + products

# psql shell against local Docker Postgres
docker exec -it tg-mini-pg psql -U postgres -d tgshop

# verify the order pipeline (server-recomputed totals are in minor units)
docker exec tg-mini-pg psql -U postgres -d tgshop -c \
  'SELECT id, total, address, status FROM "Order" ORDER BY "createdAt" DESC LIMIT 5;'
```

## Prices and currency

Prices are stored as integers in **minor units** (kopecks/cents). Render via `formatPrice(priceMinorUnits, currency)` from `src/lib/format.ts` (uses `Intl.NumberFormat`).

`Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' })` renders the seeded `149000` minor units as `1 490 ₽`. If you ever see a raw integer like `149000` or `NaN ₽` in the UI, `formatPrice` is broken or a price wasn't divided by 100 at render time.

The admin product editor accepts price in **major units** (`12.34`) and converts to minor units (`1234`) on submit. Server-side, `/api/order` always re-computes totals from DB-resolved product prices — never trust client-supplied totals.

## Common gotchas

- After moving files between route groups, run `rm -rf .next && npx tsc --noEmit` — stale `.next/types/` will report ghost "module not found" errors otherwise.
- `npm run db:seed` clears and reinserts; if you're hand-creating test data, expect it to disappear.
- Vercel preview deploys can fail if the project root is set to the old `frontend/` path. Set Root Directory to `.` in the Vercel project settings.
- Image uploads on Vercel: `/api/admin/upload` writes to `/public/uploads` which is read-only on Vercel's serverless runtime. Either swap to Vercel Blob / S3 / R2 (the contract is just `{ url: string }`) or paste an image URL directly in the admin form.
- Bot DMs require the user to have sent `/start` to the bot at least once — Telegram returns `Forbidden: bot can't initiate conversation with a user` otherwise.
