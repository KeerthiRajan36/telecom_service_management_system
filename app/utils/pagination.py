"""Generic pagination + sorting + search helpers for SQLAlchemy queries."""
import math
from typing import Any

from fastapi import Query
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Query as SAQuery

from app.core.config import settings
from app.schemas.common import PaginatedResponse


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, starting at 1"),
        page_size: int = Query(
            settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE, description="Items per page"
        ),
        sort_by: str | None = Query(None, description="Column name to sort by"),
        sort_order: str = Query("asc", pattern="^(asc|desc)$"),
        search: str | None = Query(None, description="Free-text search"),
    ):
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.search = search


def apply_search(query: SAQuery, model, search: str | None, searchable_fields: list[str]) -> SAQuery:
    if not search or not searchable_fields:
        return query
    like = f"%{search}%"
    conditions = [getattr(model, field).ilike(like) for field in searchable_fields if hasattr(model, field)]
    if conditions:
        query = query.filter(or_(*conditions))
    return query


def apply_sort(query: SAQuery, model, sort_by: str | None, sort_order: str):
    if sort_by and hasattr(model, sort_by):
        column = getattr(model, sort_by)
        query = query.order_by(desc(column) if sort_order == "desc" else asc(column))
    return query


def paginate(query: SAQuery, params: PageParams, schema, model=None, search_fields: list[str] | None = None):
    if model is not None and search_fields:
        query = apply_search(query, model, params.search, search_fields)
    if model is not None:
        query = apply_sort(query, model, params.sort_by, params.sort_order)

    total = query.count()
    items = query.offset((params.page - 1) * params.page_size).limit(params.page_size).all()
    pages = math.ceil(total / params.page_size) if params.page_size else 0

    return PaginatedResponse(
        items=[schema.model_validate(i) for i in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=pages,
    )
