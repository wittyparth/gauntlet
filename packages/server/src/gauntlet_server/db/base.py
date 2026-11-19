"""Declarative base with a stable constraint naming convention (alembic diffs stay clean)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "created_at_col", "metadata", "workspace_col"]

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING)


class Base(DeclarativeBase):
    metadata = metadata
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB, str: Text}


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def workspace_col() -> Mapped[str]:
    return mapped_column(ForeignKey("workspaces.id"))
