from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DbSession, is_admin
from app.db.models import Category, Order, OrderStatus, Product, ProductFlavor
from app.services.analytics import all_time_range, in_range, load_completed_orders, make_range, parse_date, presets, summarize
from app.services.orders import InsufficientStockError, change_order_status, get_order_for_admin
from app.services.slug import slugify

router = APIRouter(prefix="/admin")
PRODUCT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PRODUCT_IMAGE_MAX_WIDTH = 1000
PRODUCT_IMAGE_WEBP_QUALITY = 85
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
PRODUCT_UPLOAD_DIR = UPLOAD_ROOT / "products"


def admin_render(request: Request, template: str, context: dict):
    base = {"request": request, "cart_quantity": 0, "active": request.url.path}
    base.update(context)
    return request.state.templates.TemplateResponse(template, base)


def guard(admin: bool) -> RedirectResponse | None:
    return None if admin else RedirectResponse("/admin/login", status_code=303)


def product_form_redirect(product_id: str, error: str) -> RedirectResponse:
    edit_param = f"edit={product_id}&" if product_id else ""
    return RedirectResponse(f"/admin/products?{edit_param}error={error}", status_code=303)


def prepare_product_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("image_upload_invalid") from exc

    image = ImageOps.exif_transpose(image)
    if image.width > PRODUCT_IMAGE_MAX_WIDTH:
        ratio = PRODUCT_IMAGE_MAX_WIDTH / image.width
        image = image.resize((PRODUCT_IMAGE_MAX_WIDTH, round(image.height * ratio)), Image.Resampling.LANCZOS)
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    return image


async def save_product_image(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in PRODUCT_IMAGE_EXTENSIONS:
        raise ValueError("image_upload_unsupported")
    data = await upload.read()
    if not data:
        raise ValueError("image_upload_empty")
    image = prepare_product_image(data)

    PRODUCT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.webp"
    target = PRODUCT_UPLOAD_DIR / filename
    temp_target = target.with_suffix(".tmp")
    try:
        image.save(temp_target, "WEBP", quality=PRODUCT_IMAGE_WEBP_QUALITY, method=6)
        temp_target.replace(target)
    except OSError as exc:
        temp_target.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise ValueError("image_upload_invalid") from exc
    return f"/uploads/products/{filename}"


def delete_local_product_image(image_url: str | None) -> None:
    if not image_url or not image_url.startswith("/uploads/products/"):
        return
    target = PRODUCT_UPLOAD_DIR / Path(image_url).name
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass


@router.get("/login")
def login_page(request: Request, admin: Annotated[bool, Depends(is_admin)], next: str = "/admin"):
    if admin:
        return RedirectResponse(next if next.startswith("/admin") else "/admin", status_code=303)
    return request.state.templates.TemplateResponse("admin/login.html", {"request": request, "next": next})


@router.get("")
@router.get("/")
def dashboard(request: Request, db: DbSession, admin: Annotated[bool, Depends(is_admin)]):
    if redirect := guard(admin):
        return redirect
    product_count = db.scalar(select(func.count(Product.id))) or 0
    category_count = db.scalar(select(func.count(Category.id))) or 0
    order_count = db.scalar(select(func.count(Order.id))) or 0
    pending_count = db.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING)) or 0
    orders = db.scalars(select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc()).limit(5)).all()
    return admin_render(
        request,
        "admin/dashboard.html",
        {
            "product_count": product_count,
            "category_count": category_count,
            "order_count": order_count,
            "pending_count": pending_count,
            "orders": orders,
        },
    )


@router.get("/categories")
def categories_page(request: Request, db: DbSession, admin: Annotated[bool, Depends(is_admin)]):
    if redirect := guard(admin):
        return redirect
    categories = db.scalars(select(Category).order_by(Category.sort_order.asc(), Category.name.asc())).all()
    counts = dict(db.execute(select(Product.category_id, func.count(Product.id)).group_by(Product.category_id)).all())
    return admin_render(request, "admin/categories.html", {"categories": categories, "counts": counts, "editing": None})


@router.get("/categories/{category_id}/edit")
def edit_category_page(request: Request, db: DbSession, category_id: str, admin: Annotated[bool, Depends(is_admin)]):
    if redirect := guard(admin):
        return redirect
    categories = db.scalars(select(Category).order_by(Category.sort_order.asc(), Category.name.asc())).all()
    counts = dict(db.execute(select(Product.category_id, func.count(Product.id)).group_by(Product.category_id)).all())
    return admin_render(request, "admin/categories.html", {"categories": categories, "counts": counts, "editing": db.get(Category, category_id)})


@router.post("/categories")
def save_category(
    db: DbSession,
    admin: Annotated[bool, Depends(is_admin)],
    name: Annotated[str, Form()],
    slug: Annotated[str, Form()] = "",
    image_url: Annotated[str, Form()] = "",
    sort_order: Annotated[int, Form()] = 0,
    category_id: Annotated[str, Form()] = "",
):
    if redirect := guard(admin):
        return redirect
    category = db.get(Category, category_id) if category_id else Category()
    if not category_id:
        db.add(category)
    category.name = name.strip()
    base_slug = slugify(slug or name)
    candidate = base_slug
    i = 1
    while db.scalar(select(Category).where(Category.slug == candidate, Category.id != (category.id or ""))) is not None:
        i += 1
        candidate = f"{base_slug}-{i}"
    category.slug = candidate
    category.image_url = image_url.strip() or None
    category.sort_order = sort_order
    db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{category_id}/delete")
def delete_category(db: DbSession, category_id: str, admin: Annotated[bool, Depends(is_admin)]):
    if redirect := guard(admin):
        return redirect
    category = db.get(Category, category_id)
    if category is not None:
        db.delete(category)
        db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.get("/products")
def products_page(request: Request, db: DbSession, admin: Annotated[bool, Depends(is_admin)], edit: str | None = None):
    if redirect := guard(admin):
        return redirect
    products = db.scalars(select(Product).options(selectinload(Product.category), selectinload(Product.flavors)).order_by(Product.created_at.desc())).all()
    categories = db.scalars(select(Category).order_by(Category.sort_order.asc(), Category.name.asc())).all()
    editing = db.scalar(select(Product).where(Product.id == edit).options(selectinload(Product.category), selectinload(Product.flavors))) if edit else None
    return admin_render(request, "admin/products.html", {"products": products, "categories": categories, "editing": editing})


def to_minor(value: str) -> int:
    return int(round(float((value or "0").replace(",", ".")) * 100))


@router.post("/products")
async def save_product(request: Request, db: DbSession, admin: Annotated[bool, Depends(is_admin)]):
    if redirect := guard(admin):
        return redirect
    form = await request.form()
    product_id = str(form.get("product_id") or "")
    product = db.get(Product, product_id) if product_id else Product()
    replaced_image_url: str | None = None
    if not product_id:
        db.add(product)
    product.name = str(form.get("name") or "").strip()
    product.description = str(form.get("description") or "").strip() or None
    product.category_id = str(form.get("category_id") or "")
    product.price = to_minor(str(form.get("price") or "0"))
    product.cost_price = to_minor(str(form.get("cost_price") or "0"))
    product.currency = str(form.get("currency") or "RUB").strip() or "RUB"
    image_upload = form.get("image_upload")
    if hasattr(image_upload, "filename") and hasattr(image_upload, "read") and image_upload.filename:
        replaced_image_url = product.image_url
        try:
            product.image_url = await save_product_image(image_upload)
        except ValueError as exc:
            return product_form_redirect(product_id, str(exc))
    product.is_active = form.get("is_active") == "on"
    product.is_sale = form.get("is_sale") == "on"
    old_price = str(form.get("old_price") or "")
    sale_price = str(form.get("sale_price") or "")
    product.old_price = to_minor(old_price) if old_price.strip() else None
    product.sale_price = to_minor(sale_price) if sale_price.strip() else None
    product.sale_badge = str(form.get("sale_badge") or "").strip() or None
    db.flush()

    flavor_ids = [str(value) for value in form.getlist("flavor_id")]
    flavor_names = [str(value) for value in form.getlist("flavor_name")]
    flavor_stocks = [str(value) for value in form.getlist("flavor_stock")]
    deleted_ids = {str(value) for value in form.getlist("flavor_delete")}
    existing = {flavor.id: flavor for flavor in product.flavors}
    seen_names: set[str] = set()

    for flavor_id in deleted_ids:
        flavor = existing.pop(flavor_id, None)
        if flavor is not None:
            db.delete(flavor)

    for index, raw_name in enumerate(flavor_names):
        flavor_id = flavor_ids[index] if index < len(flavor_ids) else ""
        if flavor_id in deleted_ids:
            continue
        name = raw_name.strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        raw_stock = flavor_stocks[index] if index < len(flavor_stocks) else "0"
        try:
            stock_quantity = max(0, int(raw_stock))
        except ValueError:
            stock_quantity = 0
        flavor = existing.pop(flavor_id, None) if flavor_id else None
        if flavor is None:
            flavor = ProductFlavor(product_id=product.id)
            db.add(flavor)
        flavor.name = name
        flavor.stock_quantity = stock_quantity

    for flavor in existing.values():
        db.delete(flavor)

    db.commit()
    delete_local_product_image(replaced_image_url)
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/delete")
def delete_product(db: DbSession, product_id: str, admin: Annotated[bool, Depends(is_admin)]):
    if redirect := guard(admin):
        return redirect
    product = db.get(Product, product_id)
    if product is not None:
        image_url = product.image_url
        db.delete(product)
        db.commit()
        delete_local_product_image(image_url)
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/orders")
def orders_page(request: Request, db: DbSession, admin: Annotated[bool, Depends(is_admin)], status: str | None = None):
    if redirect := guard(admin):
        return redirect
    query = select(Order).options(selectinload(Order.items), selectinload(Order.status_history)).order_by(Order.created_at.desc())
    if status in OrderStatus.__members__:
        query = query.where(Order.status == OrderStatus[status])
    orders = db.scalars(query).all()
    return admin_render(request, "admin/orders.html", {"orders": orders, "status": status})


@router.post("/orders/{order_id}/status")
def order_status(db: DbSession, order_id: str, admin: Annotated[bool, Depends(is_admin)], status: Annotated[OrderStatus, Form()]):
    if redirect := guard(admin):
        return redirect
    order = get_order_for_admin(db, order_id)
    if order is not None:
        try:
            change_order_status(db, order, status)
            db.commit()
        except InsufficientStockError:
            db.rollback()
    return RedirectResponse("/admin/orders", status_code=303)


@router.get("/analytics")
def analytics_page(
    request: Request,
    db: DbSession,
    admin: Annotated[bool, Depends(is_admin)],
    date_value: Annotated[str | None, Query(alias="date")] = None,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
    range: Annotated[str | None, Query(alias="range")] = None,
):
    if redirect := guard(admin):
        return redirect
    all_orders = load_completed_orders(db)
    preset_ranges = presets()
    today = date.today()
    selected_range = all_time_range() if range == "allTime" else make_range(parse_date(date_value) or parse_date(from_date) or today, parse_date(date_value) or parse_date(to_date) or today)
    return admin_render(
        request,
        "admin/analytics.html",
        {
            "presets": {key: summarize(all_orders, value) for key, value in preset_ranges.items()},
            "selected": summarize(all_orders, selected_range),
            "orders": [order for order in all_orders if in_range(order, selected_range)],
        },
    )
