"""Pagination shared by all list endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(50, ge=1, le=500, description="Maximum rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
