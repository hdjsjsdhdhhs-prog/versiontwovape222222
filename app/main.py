from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.templating import Jinja2Templates

from app.routes import admin, auth, shop
from app.services.cart import CART_COOKIE, read_cart
from app.services.pricing import display_price, format_price, old_display_price, sale_badge

BASE_DIR = Path(__file__).resolve().parent
STATIC_VERSION = str(
    int(
        max(
            (BASE_DIR / "static" / "shop.js").stat().st_mtime,
            (BASE_DIR / "static" / "styles.css").stat().st_mtime,
        )
    )
)

app = FastAPI(title="Telegram Mini Shop", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=512)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(
    display_price=display_price,
    old_display_price=old_display_price,
    sale_badge=sale_badge,
    format_price=format_price,
    static_version=STATIC_VERSION,
)


@app.middleware("http")
async def add_template_context(request: Request, call_next):
    request.state.templates = templates
    request.state.cart_items = read_cart(request.cookies.get(CART_COOKIE))
    request.state.cart_quantity = 0
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(shop.router)
app.include_router(admin.router)


@app.exception_handler(401)
async def unauthorized(_request: Request, _exc):
    return RedirectResponse("/", status_code=303)
