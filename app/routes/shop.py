from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import exists, select
from sqlalchemy.orm import selectinload

from app.deps import DbSession
from app.db.models import Category, DeliveryMethod, Order, PaymentMethod, Product, ProductFlavor
from app.services.cart import CART_COOKIE, CartState, clamp_cart_quantity, read_cart, resolve_cart, write_cart
from app.services.orders import InsufficientStockError, OrderError, create_order

router = APIRouter()
CART_MAX_AGE = 60 * 60 * 24 * 30
CUSTOMER_PAYMENT_METHODS = {PaymentMethod.CASH.value, PaymentMethod.CARD.value}
OUT_OF_STOCK_NOTICE = "out_of_stock"


def add_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def remove_query_param(url: str, key: str) -> str:
    parts = urlsplit(url)
    query = [(name, value) for name, value in parse_qsl(parts.query, keep_blank_values=True) if name != key]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def out_of_stock_redirect(url: str) -> RedirectResponse:
    return RedirectResponse(add_query_param(url, "notice", OUT_OF_STOCK_NOTICE), status_code=303)


def sync_cart_cookie(response: Response, old_items: dict[str, int], new_items: dict[str, int]) -> Response:
    if old_items == new_items:
        return response
    if new_items:
        response.set_cookie(CART_COOKIE, write_cart(new_items), max_age=CART_MAX_AGE, samesite="lax", path="/")
    else:
        response.delete_cookie(CART_COOKIE, path="/")
    return response


def render(request: Request, db: DbSession, template: str, context: dict, cart_state: CartState | None = None):
    old_items = request.state.cart_items
    cart_state = cart_state or resolve_cart(db, old_items)
    request.state.cart_items = cart_state.items
    request.state.cart_quantity = cart_state.quantity
    base = {"request": request, "cart_quantity": cart_state.quantity}
    base.update(context)
    response = request.state.templates.TemplateResponse(template, base)
    return sync_cart_cookie(response, old_items, cart_state.items)


@router.get("/")
def home(request: Request, db: DbSession):
    categories = db.scalars(select(Category).order_by(Category.sort_order.asc(), Category.name.asc())).all()
    available_flavor = exists().where(ProductFlavor.product_id == Product.id, ProductFlavor.stock_quantity > 0)
    sale_products = db.scalars(
        select(Product)
        .where(Product.is_sale.is_(True), Product.is_active.is_(True), available_flavor)
        .options(selectinload(Product.flavors))
        .order_by(Product.updated_at.desc(), Product.created_at.desc())
        .limit(24)
    ).all()
    return render(request, db, "shop/home.html", {"categories": categories, "sale_products": sale_products})


@router.get("/category/{category_id}")
def category_page(request: Request, db: DbSession, category_id: str):
    category = db.get(Category, category_id)
    if category is None:
        return RedirectResponse("/", status_code=303)
    available_flavor = exists().where(ProductFlavor.product_id == Product.id, ProductFlavor.stock_quantity > 0)
    products = db.scalars(
        select(Product)
        .where(Product.category_id == category_id, Product.is_active.is_(True), available_flavor)
        .options(selectinload(Product.flavors))
        .order_by(Product.created_at.desc())
    ).all()
    return render(request, db, "shop/category.html", {"category": category, "products": products})


@router.get("/product/{product_id}")
def product_page(request: Request, db: DbSession, product_id: str):
    product = db.scalar(select(Product).where(Product.id == product_id).options(selectinload(Product.category), selectinload(Product.flavors)))
    if product is None or not product.is_active:
        return RedirectResponse("/", status_code=303)
    return render(request, db, "shop/product.html", {"product": product})


@router.post("/cart/add/{product_id}")
def add_to_cart(request: Request, db: DbSession, product_id: str, flavor_id: Annotated[str, Form()] = ""):
    redirect_url = remove_query_param(request.headers.get("referer", "/cart"), "notice")
    items = read_cart(request.cookies.get(CART_COOKIE))
    old_items = dict(items)
    flavor = db.scalar(
        select(ProductFlavor)
        .where(ProductFlavor.id == flavor_id, ProductFlavor.product_id == product_id)
        .options(selectinload(ProductFlavor.product))
    )
    if flavor is None or flavor.product is None or not flavor.product.is_active or flavor.stock_quantity <= 0:
        response = out_of_stock_redirect(redirect_url)
        return sync_cart_cookie(response, old_items, resolve_cart(db, items).items)
    current_quantity = items.get(flavor.id, 0)
    next_quantity = clamp_cart_quantity(current_quantity + 1, flavor.stock_quantity)
    if next_quantity <= current_quantity:
        response = out_of_stock_redirect(redirect_url)
        return sync_cart_cookie(response, old_items, resolve_cart(db, items).items)
    items[flavor.id] = next_quantity
    cart_state = resolve_cart(db, items)
    response = RedirectResponse(redirect_url, status_code=303)
    response.set_cookie(CART_COOKIE, write_cart(cart_state.items), max_age=CART_MAX_AGE, samesite="lax", path="/")
    return response


@router.post("/cart/update/{flavor_id}")
def update_cart(request: Request, db: DbSession, flavor_id: str, quantity: Annotated[int, Form()]):
    items = read_cart(request.cookies.get(CART_COOKIE))
    old_items = dict(items)
    show_out_of_stock = False
    if quantity <= 0:
        items.pop(flavor_id, None)
    else:
        flavor = db.scalar(select(ProductFlavor).where(ProductFlavor.id == flavor_id).options(selectinload(ProductFlavor.product)))
        if flavor is None or flavor.product is None or not flavor.product.is_active or flavor.stock_quantity <= 0:
            items.pop(flavor_id, None)
            show_out_of_stock = True
        else:
            next_quantity = clamp_cart_quantity(quantity, flavor.stock_quantity)
            if next_quantity < quantity:
                show_out_of_stock = True
            items[flavor_id] = next_quantity
    cart_state = resolve_cart(db, items)
    if quantity > 0 and cart_state.items.get(flavor_id, 0) < quantity:
        show_out_of_stock = True
    response = out_of_stock_redirect("/cart") if show_out_of_stock else RedirectResponse("/cart", status_code=303)
    return sync_cart_cookie(response, old_items, cart_state.items)


@router.post("/cart/clear")
def clear_cart():
    response = RedirectResponse("/cart", status_code=303)
    response.delete_cookie(CART_COOKIE, path="/")
    return response


@router.get("/cart")
def cart_page(request: Request, db: DbSession):
    cart_state = resolve_cart(db, request.state.cart_items)
    return render(
        request,
        db,
        "shop/cart.html",
        {"lines": cart_state.lines, "total": cart_state.total, "currency": cart_state.currency},
        cart_state,
    )


@router.get("/checkout")
def checkout_page(request: Request, db: DbSession):
    cart_state = resolve_cart(db, request.state.cart_items)
    if not cart_state.lines:
        response = RedirectResponse("/cart", status_code=303)
        return sync_cart_cookie(response, request.state.cart_items, cart_state.items)
    return render(
        request,
        db,
        "shop/checkout.html",
        {
            "lines": cart_state.lines,
            "total": cart_state.total,
            "currency": cart_state.currency,
        },
        cart_state,
    )


@router.post("/order")
def place_order(
    request: Request,
    db: DbSession,
    telegram_username: Annotated[str, Form(alias="telegram_username")],
    payment_method: Annotated[str, Form()],
    delivery_method: Annotated[DeliveryMethod, Form()],
    address: Annotated[str, Form()] = "",
    comment: Annotated[str, Form()] = "",
):
    old_items = request.state.cart_items
    cart_state = resolve_cart(db, request.state.cart_items)
    request.state.cart_items = cart_state.items
    request.state.cart_quantity = cart_state.quantity
    if not cart_state.lines:
        response = RedirectResponse("/checkout?error=empty_cart", status_code=303)
        return sync_cart_cookie(response, old_items, cart_state.items)
    if payment_method not in CUSTOMER_PAYMENT_METHODS:
        return RedirectResponse("/checkout?error=payment_method_invalid", status_code=303)
    customer_payment_method = PaymentMethod(payment_method)
    try:
        order = create_order(db, telegram_username, cart_state.items, customer_payment_method, delivery_method, address, comment)
        db.commit()
    except InsufficientStockError as exc:
        db.rollback()
        return RedirectResponse(f"/checkout?error={str(exc)}", status_code=303)
    except OrderError as exc:
        db.rollback()
        return RedirectResponse(f"/checkout?error={str(exc)}", status_code=303)
    response = RedirectResponse(f"/orders/success?order={order.id}", status_code=303)
    response.delete_cookie(CART_COOKIE, path="/")
    return response


@router.get("/orders/success")
def order_success(request: Request, db: DbSession, order: str | None = None):
    saved = db.scalar(select(Order).where(Order.id == order).options(selectinload(Order.items))) if order else None
    return render(request, db, "shop/success.html", {"order": saved})
