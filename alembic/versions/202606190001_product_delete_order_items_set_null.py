"""allow deleting products referenced by orders

Revision ID: 202606190001
Revises: 202606140002
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606190001"
down_revision: str | None = "202606140002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("order_items_product_id_fkey", "order_items", type_="foreignkey")
    op.alter_column("order_items", "product_id", existing_type=sa.String(length=32), nullable=True)
    op.create_foreign_key(
        "order_items_product_id_fkey",
        "order_items",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("order_items_product_id_fkey", "order_items", type_="foreignkey")
    op.execute('DELETE FROM order_items WHERE product_id IS NULL')
    op.alter_column("order_items", "product_id", existing_type=sa.String(length=32), nullable=False)
    op.create_foreign_key("order_items_product_id_fkey", "order_items", "products", ["product_id"], ["id"])
