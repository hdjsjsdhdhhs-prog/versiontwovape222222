"""product flavor inventory

Revision ID: 202606140002
Revises: 202606140001
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606140002"
down_revision: str | None = "202606140001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_flavors",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "name", name="uq_product_flavors_product_name"),
    )
    op.create_index(op.f("ix_product_flavors_product_id"), "product_flavors", ["product_id"], unique=False)
    op.create_index(op.f("ix_product_flavors_stock_quantity"), "product_flavors", ["stock_quantity"], unique=False)

    op.execute(
        """
        INSERT INTO product_flavors (id, product_id, name, stock_quantity, created_at, updated_at)
        SELECT
            substr(md5(id || '-default-flavor'), 1, 32),
            id,
            'Default',
            GREATEST(stock_quantity, 0),
            now(),
            now()
        FROM products
        """
    )

    op.add_column("order_items", sa.Column("flavor_id", sa.String(length=32), nullable=True))
    op.add_column("order_items", sa.Column("flavor_name", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_order_items_flavor_id"), "order_items", ["flavor_id"], unique=False)
    op.create_foreign_key("order_items_flavor_id_fkey", "order_items", "product_flavors", ["flavor_id"], ["id"], ondelete="SET NULL")

    op.execute(
        """
        UPDATE order_items
        SET
            flavor_id = product_flavors.id,
            flavor_name = product_flavors.name
        FROM product_flavors
        WHERE order_items.product_id = product_flavors.product_id
        """
    )
    op.execute("UPDATE order_items SET flavor_name = 'Default' WHERE flavor_name IS NULL")
    op.alter_column("order_items", "flavor_name", nullable=False)

    op.drop_index(op.f("ix_products_stock_quantity"), table_name="products")
    op.drop_index(op.f("ix_products_in_stock"), table_name="products")
    op.drop_column("products", "stock_quantity")
    op.drop_column("products", "in_stock")


def downgrade() -> None:
    op.add_column("products", sa.Column("in_stock", sa.Boolean(), nullable=True))
    op.add_column("products", sa.Column("stock_quantity", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE products
        SET stock_quantity = COALESCE(stock.total_stock, 0),
            in_stock = COALESCE(stock.total_stock, 0) > 0
        FROM (
            SELECT product_id, SUM(stock_quantity) AS total_stock
            FROM product_flavors
            GROUP BY product_id
        ) AS stock
        WHERE products.id = stock.product_id
        """
    )
    op.execute("UPDATE products SET stock_quantity = 0 WHERE stock_quantity IS NULL")
    op.execute("UPDATE products SET in_stock = false WHERE in_stock IS NULL")
    op.alter_column("products", "stock_quantity", nullable=False)
    op.alter_column("products", "in_stock", nullable=False)
    op.create_index(op.f("ix_products_stock_quantity"), "products", ["stock_quantity"], unique=False)
    op.create_index(op.f("ix_products_in_stock"), "products", ["in_stock"], unique=False)

    op.drop_constraint("order_items_flavor_id_fkey", "order_items", type_="foreignkey")
    op.drop_index(op.f("ix_order_items_flavor_id"), table_name="order_items")
    op.drop_column("order_items", "flavor_name")
    op.drop_column("order_items", "flavor_id")

    op.drop_index(op.f("ix_product_flavors_stock_quantity"), table_name="product_flavors")
    op.drop_index(op.f("ix_product_flavors_product_id"), table_name="product_flavors")
    op.drop_table("product_flavors")
